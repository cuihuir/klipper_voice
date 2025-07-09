# Klipper Voice Control Plugin
#
# This plugin provides voice announcement functionality for Klipper
# through G-code commands and event triggers.
#
# Features:
# - Voice announcements for print events (start, end, pause, resume, cancel)
# - Custom voice messages through G-code commands
# - Configurable volume, speed, and language settings
# - Auto-announcement settings for different events
# - Web API endpoints for remote control
# - Queue management to prevent overlapping announcements
#
# Copyright (C) 2024  Klipper Voice Plugin
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import json
import time
import os
import subprocess
import threading

class KlipperVoice:
    """
    Main voice control plugin class.
    
    This class manages all voice announcement functionality including:
    - Configuration management
    - Event handling
    - G-code command registration
    - Web API endpoints
    - Audio output simulation (for testing)
    """
    def __init__(self, config):
        """
        Initialize the voice plugin.
        
        Args:
            config: Configuration object containing plugin settings
        """
        # Get printer object reference for accessing other Klipper components
        self.printer = config.get_printer()
        
        # Get plugin name from configuration (usually 'klipper_voice')
        self.name = config.get_name()
        
        # === Configuration Parameters ===
        # Enable/disable voice announcements globally
        self.enabled = config.getboolean('enabled', True)
        
        # Volume level (0.0 = mute, 1.0 = maximum)
        self.volume = config.getfloat('volume', 0.8, minval=0.0, maxval=1.0)
        
        # Language code for voice synthesis (e.g., 'en', 'zh', 'es')
        self.language = config.get('language', 'en')
        
        # Voice playback speed (0.5 = slow, 2.0 = fast)
        self.voice_speed = config.getfloat('voice_speed', 1.0, minval=0.5, maxval=2.0)
        
        # === Audio File Configuration ===
        # Base directory for audio files
        self.audio_base_path = config.get('audio_path', '/home/pi/klipper_voice_files')
        
        # Supported audio formats (auto-detected)
        self.supported_formats = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac']
        
        # Audio player priority list (will auto-detect best available)
        self.audio_players = {
            'ffmpeg': {
                'command': 'ffmpeg',
                'args': ['-i', '{file}', '-f', 'alsa', 'default', '-v', 'quiet'],
                'volume_support': True,
                'formats': ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma']
            },
            'mpg123': {
                'command': 'mpg123',
                'args': ['-q', '{file}'],
                'volume_support': True,
                'formats': ['mp3']
            },
            'aplay': {
                'command': 'aplay',
                'args': ['-q', '{file}'],
                'volume_support': False,
                'formats': ['wav']
            },
            'paplay': {
                'command': 'paplay',
                'args': ['{file}'],
                'volume_support': True,
                'formats': ['wav', 'ogg', 'flac']
            },
            'cvlc': {
                'command': 'cvlc',
                'args': ['--intf', 'dummy', '--play-and-exit', '{file}'],
                'volume_support': True,
                'formats': ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac']
            }
        }
        
        # Auto-detected audio player (will be set during initialization)
        self.selected_player = None
        
        # Enable hardware volume control through player
        self.use_hardware_volume = config.getboolean('use_hardware_volume', True)
        
        # === Voice Message Templates ===
        # Predefined messages for different events, customizable via config
        self.voice_messages = {
            'print_start': config.get('msg_print_start', 'Print started'),
            'print_end': config.get('msg_print_end', 'Print completed'),
            'print_pause': config.get('msg_print_pause', 'Print paused'),
            'print_resume': config.get('msg_print_resume', 'Print resumed'),
            'print_cancel': config.get('msg_print_cancel', 'Print cancelled'),
            'filament_runout': config.get('msg_filament_runout', 'Filament runout detected'),
            'error': config.get('msg_error', 'Error occurred'),
            'ready': config.get('msg_ready', 'Printer ready'),
            'heating': config.get('msg_heating', 'Heating started'),
            'temp_reached': config.get('msg_temp_reached', 'Target temperature reached')
        }
        
        # === Auto-announcement Settings ===
        # Control which events trigger automatic announcements
        self.auto_announce = {
            'print_start': config.getboolean('auto_print_start', True),
            'print_end': config.getboolean('auto_print_end', True),
            'print_pause': config.getboolean('auto_print_pause', True),
            'print_resume': config.getboolean('auto_print_resume', True),
            'print_cancel': config.getboolean('auto_print_cancel', True),
            'filament_runout': config.getboolean('auto_filament_runout', True),
            'error': config.getboolean('auto_error', False),  # Disabled by default to avoid spam
            'ready': config.getboolean('auto_ready', True)
        }
        
        # === State Tracking Variables ===
        # Track the last announcement to prevent duplicates
        self.last_announcement = None
        
        # Timestamp of last announcement for rate limiting
        self.last_announcement_time = 0
        
        # Minimum time between announcements (prevents spam)
        self.min_announcement_interval = config.getfloat('min_interval', 2.0, minval=0.1)
        
        # Queue for managing multiple announcements (future enhancement)
        self.announcement_queue = []
        
        # === Audio Playback State ===
        # Track current playback process
        self.current_playback_process = None
        
        # Lock for thread-safe audio operations
        self.playback_lock = threading.Lock()
        
        # Audio file mapping cache
        self.audio_file_cache = {}
        
        # === Event Handler Registration ===
        # Register handlers for Klipper system events
        self.printer.register_event_handler("klippy:connect", self.handle_connect)
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self.handle_shutdown)
        
        # === Initialize Logging ===
        # Create logger instance for this plugin
        self.logger = logging.getLogger(__name__)
        
        # === Initialize Audio System ===
        self._initialize_audio_system()
        
        self.logger.info("KlipperVoice plugin initialized - enabled: %s, volume: %.1f", 
                        self.enabled, self.volume)
    
    def _initialize_audio_system(self):
        """
        Initialize audio system and validate configuration.
        
        This method:
        - Creates audio file directory if needed
        - Validates audio player availability
        - Scans for available audio files
        - Builds audio file cache
        """
        # === Create Audio Directory ===
        try:
            if not os.path.exists(self.audio_base_path):
                os.makedirs(self.audio_base_path, exist_ok=True)
                self.logger.info("Created audio directory: %s", self.audio_base_path)
        except Exception as e:
            self.logger.error("Failed to create audio directory %s: %s", 
                            self.audio_base_path, str(e))
        
        # === Auto-detect Best Audio Player ===
        self._detect_audio_player()
        
        # === Scan Audio Files ===
        self._scan_audio_files()
    
    def _detect_audio_player(self):
        """
        Auto-detect the best available audio player.
        
        Priority order:
        1. ffmpeg (most versatile, supports all formats)
        2. mpg123 (good for MP3)
        3. paplay (PulseAudio)
        4. cvlc (VLC)
        5. aplay (basic ALSA)
        
        Sets self.selected_player to the best available option.
        """
        # Priority order for audio players
        priority_order = ['ffmpeg', 'mpg123', 'paplay', 'cvlc', 'aplay']
        
        for player_name in priority_order:
            if player_name not in self.audio_players:
                continue
                
            player_config = self.audio_players[player_name]
            command = player_config['command']
            
            try:
                # Check if the command is available
                result = subprocess.run(['which', command], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.selected_player = player_name
                    self.logger.info("Selected audio player: %s (%s)", 
                                   player_name, command)
                    self.logger.info("Supported formats: %s", 
                                   ', '.join(player_config['formats']))
                    return
            except Exception as e:
                self.logger.debug("Error checking %s: %s", command, str(e))
        
        # No audio player found
        self.selected_player = None
        self.logger.warning("No audio player found. Available players: %s", 
                          ', '.join(priority_order))
        self.logger.warning("Voice announcements will be logged only")
        self.logger.info("To install audio players, try:")
        self.logger.info("  sudo apt install ffmpeg          # (recommended)")
        self.logger.info("  sudo apt install mpg123")
        self.logger.info("  sudo apt install pulseaudio-utils")
        self.logger.info("  sudo apt install vlc")
    
    def _scan_audio_files(self):
        """
        Scan audio directory for available files and build cache.
        
        Creates mapping between message types and audio file paths.
        Expected filename format: <message_type>.<language>.<format>
        Example: print_start.en.mp3, print_end.zh.mp3
        """
        self.audio_file_cache = {}
        
        if not os.path.exists(self.audio_base_path):
            self.logger.warning("Audio directory does not exist: %s", self.audio_base_path)
            return
        
        try:
            for filename in os.listdir(self.audio_base_path):
                # Check if file has supported format
                file_ext = filename.split('.')[-1].lower()
                if file_ext not in self.supported_formats:
                    continue
                
                # Parse filename: message_type.language.format
                name_parts = filename.rsplit('.', 2)
                if len(name_parts) >= 2:
                    message_type = name_parts[0]
                    language = name_parts[1] if len(name_parts) == 3 else 'default'
                    format_ext = name_parts[-1].lower()
                    
                    # Build file path
                    file_path = os.path.join(self.audio_base_path, filename)
                    
                    # Store in cache with format info
                    if message_type not in self.audio_file_cache:
                        self.audio_file_cache[message_type] = {}
                    if language not in self.audio_file_cache[message_type]:
                        self.audio_file_cache[message_type][language] = {}
                    
                    self.audio_file_cache[message_type][language][format_ext] = file_path
                    
                    self.logger.debug("Found audio file: %s -> %s (%s, %s)", 
                                    message_type, file_path, language, format_ext)
            
            self.logger.info("Audio file scan complete. Found %d message types", 
                           len(self.audio_file_cache))
            
        except Exception as e:
            self.logger.error("Error scanning audio files: %s", str(e))
    
    def handle_connect(self):
        """
        Handle Klipper connection event.
        
        This method is called when Klipper is fully connected and ready.
        It registers G-code commands, webhook endpoints, and print event handlers.
        """
        # === Register G-code Commands ===
        # Get the G-code object for command registration
        gcode = self.printer.lookup_object('gcode')
        
        # Register voice control commands
        gcode.register_command("VOICE_ANNOUNCE", self.cmd_VOICE_ANNOUNCE,
                              desc=self.cmd_VOICE_ANNOUNCE_help)
        gcode.register_command("VOICE_CONFIG", self.cmd_VOICE_CONFIG,
                              desc=self.cmd_VOICE_CONFIG_help)
        gcode.register_command("VOICE_STATUS", self.cmd_VOICE_STATUS,
                              desc=self.cmd_VOICE_STATUS_help)
        gcode.register_command("VOICE_TEST", self.cmd_VOICE_TEST,
                              desc=self.cmd_VOICE_TEST_help)
        gcode.register_command("VOICE_SCAN", self.cmd_VOICE_SCAN,
                              desc=self.cmd_VOICE_SCAN_help)
        
        # === Register Web API Endpoints ===
        # Get webhooks object for API endpoint registration
        webhooks = self.printer.lookup_object('webhooks')
        
        # Register REST API endpoints for remote control
        webhooks.register_endpoint("voice/announce", self._handle_announce_request)
        webhooks.register_endpoint("voice/config", self._handle_config_request)
        webhooks.register_endpoint("voice/status", self._handle_status_request)
        
        # === Register Print Event Handlers ===
        # Try to register with virtual_sdcard for print events
        # This allows automatic announcements for print start/end/pause/resume
        try:
            virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
            if virtual_sdcard:
                self.printer.register_event_handler("print_stats", self._handle_print_event)
        except:
            # If virtual_sdcard is not available, continue without print event integration
            self.logger.warning("Could not register print event handlers")
        
        self.logger.info("KlipperVoice connected and ready")
    
    def handle_ready(self):
        """
        Handle Klipper ready event.
        
        Called when Klipper is fully initialized and ready to accept commands.
        Announces readiness if auto-announce is enabled.
        """
        if self.enabled and self.auto_announce.get('ready', True):
            self._announce_message('ready')
    
    def handle_shutdown(self):
        """
        Handle Klipper shutdown event.
        
        Called when Klipper is shutting down. Cleanup any resources if needed.
        """
        # === Stop Current Playback ===
        self._stop_current_playback()
        
        self.logger.info("KlipperVoice shutting down")
    
    def _can_announce(self):
        """
        Check if announcement is allowed based on timing and state.
        
        Returns:
            bool: True if announcement is allowed, False otherwise
            
        Checks:
            - Plugin is enabled
            - Minimum interval has passed since last announcement
        """
        # Check if plugin is globally enabled
        if not self.enabled:
            return False
        
        # Check minimum interval to prevent spam
        current_time = time.time()
        if (current_time - self.last_announcement_time) < self.min_announcement_interval:
            return False
        
        return True
    
    def _announce_message(self, message_type, custom_message=None):
        """
        Core announcement function - handles all voice announcements.
        
        Args:
            message_type (str): Type of message (e.g., 'print_start', 'print_end')
            custom_message (str, optional): Custom message text to override default
            
        Returns:
            bool: True if announcement was made, False if blocked
            
        This is the main function that processes all voice announcements.
        It handles rate limiting, message retrieval, and audio output simulation.
        """
        # Check if announcement is allowed (rate limiting, enabled state)
        if not self._can_announce():
            self.logger.debug("Announcement blocked - too frequent or disabled")
            return False
        
        # === Message Text Retrieval ===
        # Use custom message if provided, otherwise use predefined message
        if custom_message:
            message_text = custom_message
        else:
            message_text = self.voice_messages.get(message_type, "Unknown message")
        
        # === Logging for Debug/Testing ===
        # Log the announcement with all parameters for testing
        self.logger.info("VOICE ANNOUNCEMENT [%s]: %s (volume: %.1f, speed: %.1f, lang: %s)", 
                        message_type.upper(), message_text, self.volume, self.voice_speed, self.language)
        
        # === State Updates ===
        # Update tracking variables
        self.last_announcement = message_type
        self.last_announcement_time = time.time()
        
        # === Audio Output ===
        # Play actual audio file or fall back to simulation
        audio_played = self._play_audio_file(message_type)
        
        # Keep simulation for logging and fallback
        self._simulate_audio_output(message_text)
        
        return True
    
    def _simulate_audio_output(self, message):
        """
        Play actual audio output using predefined audio files.
        
        Args:
            message (str): The message text (for logging purposes)
            
        This function handles the actual audio playback using pre-recorded
        audio files. It falls back to logging if audio files are not available.
        """
        # Log the message for debugging
        self.logger.info("🔊 AUDIO OUTPUT: '%s'", message)
        self.logger.debug("Audio settings - Volume: %.1f, Speed: %.1f, Language: %s", 
                         self.volume, self.voice_speed, self.language)
        
        # Note: The actual audio file selection is handled in _play_audio_file
        # This method is kept for compatibility and logging
    
    def _play_audio_file(self, message_type):
        """
        Play audio file for the specified message type.
        
        Args:
            message_type (str): Type of message to play
            
        Returns:
            bool: True if audio was played successfully, False otherwise
            
        This method:
        - Finds appropriate audio file for message type and language
        - Stops any current playback
        - Starts new audio playback in background thread
        - Handles volume control
        """
        # === Find Audio File ===
        audio_file = self._get_audio_file_path(message_type)
        if not audio_file:
            self.logger.debug("No audio file found for message type: %s", message_type)
            return False
        
        # === Stop Current Playback ===
        self._stop_current_playback()
        
        # === Start New Playback ===
        try:
            # Start playback in background thread
            playback_thread = threading.Thread(
                target=self._execute_audio_playback, 
                args=(audio_file, message_type),
                daemon=True
            )
            playback_thread.start()
            
            self.logger.info("Started audio playback: %s -> %s", message_type, audio_file)
            return True
            
        except Exception as e:
            self.logger.error("Failed to start audio playback: %s", str(e))
            return False
    
    def _get_audio_file_path(self, message_type):
        """
        Get audio file path for message type and current language.
        
        Args:
            message_type (str): Type of message
            
        Returns:
            str: Path to audio file, or None if not found
            
        Lookup priority:
        1. message_type.current_language.supported_format
        2. message_type.en.supported_format (fallback to English)
        3. message_type.default.supported_format (generic fallback)
        4. Any available file
        """
        if message_type not in self.audio_file_cache:
            return None
        
        language_files = self.audio_file_cache[message_type]
        
        # Get supported formats for current player
        if self.selected_player:
            supported_formats = self.audio_players[self.selected_player]['formats']
        else:
            supported_formats = self.supported_formats
        
        # Try current language first
        if self.language in language_files:
            return self._get_best_format_file(language_files[self.language], supported_formats)
        
        # Fallback to English
        if 'en' in language_files:
            return self._get_best_format_file(language_files['en'], supported_formats)
        
        # Fallback to default
        if 'default' in language_files:
            return self._get_best_format_file(language_files['default'], supported_formats)
        
        # Use any available file
        for lang_formats in language_files.values():
            result = self._get_best_format_file(lang_formats, supported_formats)
            if result:
                return result
        
        return None
    
    def _get_best_format_file(self, format_files, supported_formats):
        """
        Get the best available format file for the current player.
        
        Args:
            format_files (dict): Dictionary of format -> file_path
            supported_formats (list): List of supported formats
            
        Returns:
            str: Path to best format file, or None if not found
        """
        # Try formats in order of preference
        for format_ext in supported_formats:
            if format_ext in format_files:
                return format_files[format_ext]
        
        # If no preferred format, use any available
        if format_files:
            return next(iter(format_files.values()))
        
        return None
    
    def _execute_audio_playback(self, audio_file, message_type):
        """
        Execute audio playback in background thread.
        
        Args:
            audio_file (str): Path to audio file
            message_type (str): Message type for logging
            
        This method runs in a separate thread to avoid blocking Klipper.
        It handles the actual subprocess execution for audio playback.
        """
        with self.playback_lock:
            try:
                if not self.selected_player:
                    self.logger.warning("No audio player available for playback")
                    return
                
                player_config = self.audio_players[self.selected_player]
                
                # Build command from player configuration
                cmd = [player_config['command']]
                
                # Process arguments and replace {file} placeholder
                for arg in player_config['args']:
                    if '{file}' in arg:
                        cmd.append(arg.replace('{file}', audio_file))
                    else:
                        cmd.append(arg)
                
                # Add volume control if supported
                if self.use_hardware_volume and player_config['volume_support']:
                    if self.selected_player == 'ffmpeg':
                        # FFmpeg volume control: -filter:a "volume=0.8"
                        volume_filter = f"volume={self.volume}"
                        cmd.extend(['-filter:a', volume_filter])
                    elif self.selected_player == 'mpg123':
                        # mpg123 volume control: -g <gain> (0-100)
                        gain = int(self.volume * 100)
                        cmd.extend(['-g', str(gain)])
                    elif self.selected_player == 'paplay':
                        # paplay volume control: --volume <0-65536>
                        volume = int(self.volume * 65536)
                        cmd.extend(['--volume', str(volume)])
                    elif self.selected_player == 'cvlc':
                        # VLC volume control: --volume <0-256>
                        volume = int(self.volume * 256)
                        cmd.extend(['--volume', str(volume)])
                
                self.logger.debug("Executing audio command: %s", ' '.join(cmd))
                
                # Execute playback
                self.current_playback_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Wait for completion
                stdout, stderr = self.current_playback_process.communicate(timeout=30)
                
                if self.current_playback_process.returncode == 0:
                    self.logger.debug("Audio playback completed: %s", message_type)
                else:
                    self.logger.warning("Audio playback failed: %s (return code: %d)", 
                                      message_type, self.current_playback_process.returncode)
                    if stderr:
                        self.logger.warning("Audio error output: %s", stderr.strip())
                
            except subprocess.TimeoutExpired:
                self.logger.warning("Audio playback timeout: %s", message_type)
                if self.current_playback_process:
                    self.current_playback_process.kill()
            
            except Exception as e:
                self.logger.error("Audio playback error: %s - %s", message_type, str(e))
            
            finally:
                self.current_playback_process = None
    
    def _stop_current_playback(self):
        """
        Stop any currently running audio playback.
        
        This method safely terminates the current audio playback process
        to prevent overlapping audio announcements.
        """
        if self.current_playback_process and self.current_playback_process.poll() is None:
            try:
                self.logger.debug("Stopping current audio playback")
                self.current_playback_process.terminate()
                
                # Give it a moment to terminate gracefully
                try:
                    self.current_playback_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    self.current_playback_process.kill()
                    
            except Exception as e:
                self.logger.warning("Error stopping audio playback: %s", str(e))
            
            finally:
                self.current_playback_process = None
    
    def _handle_print_event(self, event_name, event_data):
        """
        Handle print-related events from Klipper.
        
        Args:
            event_name (str): Name of the print event
            event_data (dict): Event data containing details
            
        This function receives print events from Klipper's virtual_sdcard
        and triggers appropriate voice announcements based on auto_announce settings.
        """
        self.logger.debug("Print event received: %s - %s", event_name, event_data)
        
        # === Event to Message Type Mapping ===
        # Map Klipper print events to our voice message types
        event_mapping = {
            'print_start': 'print_start',
            'print_end': 'print_end',
            'print_pause': 'print_pause',
            'print_resume': 'print_resume',
            'print_cancel': 'print_cancel'
        }
        
        # === Auto-announcement Logic ===
        # Check if this event type should trigger an announcement
        message_type = event_mapping.get(event_name)
        if message_type and self.auto_announce.get(message_type, False):
            self._announce_message(message_type)
    
    def _handle_announce_request(self, web_request):
        """
        Handle webhook announcement requests.
        
        Args:
            web_request (dict): Web request data containing message info
            
        Returns:
            dict: Response with success status and message details
            
        Web API endpoint: POST /voice/announce
        Expected parameters:
        - type: message type (optional, default: 'custom')
        - message: text to announce (required)
        """
        message_type = web_request.get('type', 'custom')
        message_text = web_request.get('message', '')
        
        if message_text:
            success = self._announce_message(message_type, message_text)
            return {'success': success, 'message': message_text}
        else:
            return {'success': False, 'error': 'No message provided'}
    
    def _handle_config_request(self, web_request):
        """
        Handle webhook configuration requests.
        
        Args:
            web_request (dict): Web request data
            
        Returns:
            dict: Current plugin configuration
            
        Web API endpoint: GET /voice/config
        Returns all current voice plugin settings.
        """
        return {
            'enabled': self.enabled,
            'volume': self.volume,
            'language': self.language,
            'voice_speed': self.voice_speed,
            'auto_announce': self.auto_announce,
            'voice_messages': self.voice_messages
        }
    
    def _handle_status_request(self, web_request):
        """
        Handle webhook status requests.
        
        Args:
            web_request (dict): Web request data
            
        Returns:
            dict: Current plugin status information
            
        Web API endpoint: GET /voice/status
        Returns runtime status including last announcements and queue state.
        """
        return {
            'enabled': self.enabled,
            'last_announcement': self.last_announcement,
            'last_announcement_time': self.last_announcement_time,
            'queue_length': len(self.announcement_queue)
        }
    
    def get_status(self, eventtime):
        """
        Return plugin status for Klipper API queries.
        
        Args:
            eventtime (float): Current event time from Klipper
            
        Returns:
            dict: Complete plugin status including configuration and runtime state
            
        This method is called by Klipper's API system to provide status information
        that can be queried by external applications like Mainsail or Fluidd.
        """
        return {
            'enabled': self.enabled,
            'volume': self.volume,
            'language': self.language,
            'voice_speed': self.voice_speed,
            'last_announcement': self.last_announcement,
            'last_announcement_time': self.last_announcement_time,
            'queue_length': len(self.announcement_queue),
            'auto_announce': self.auto_announce,
            'available_messages': list(self.voice_messages.keys()),
            'audio_player': self.selected_player,
            'supported_formats': self.supported_formats,
            'available_players': list(self.audio_players.keys())
        }
    
    # === G-code Command Implementations ===
    
    cmd_VOICE_ANNOUNCE_help = "Announce a voice message"
    def cmd_VOICE_ANNOUNCE(self, gcmd):
        """
        G-code command: VOICE_ANNOUNCE
        
        Syntax: VOICE_ANNOUNCE [MESSAGE=<text>] [TYPE=<type>] [VOLUME=<0.0-1.0>]
        
        Parameters:
        - MESSAGE: Custom text to announce (optional if TYPE is specified)
        - TYPE: Predefined message type (print_start, print_end, etc.)
        - VOLUME: Temporary volume override for this announcement
        
        Examples:
        - VOICE_ANNOUNCE MESSAGE="Custom message"
        - VOICE_ANNOUNCE TYPE=print_start
        - VOICE_ANNOUNCE MESSAGE="Loud message" VOLUME=1.0
        """
        # === Parameter Extraction ===
        message = gcmd.get('MESSAGE', None)
        message_type = gcmd.get('TYPE', 'custom')
        volume = gcmd.get_float('VOLUME', self.volume, minval=0.0, maxval=1.0)
        
        # === Message Resolution ===
        if not message:
            # Use predefined message if no custom message provided
            if message_type in self.voice_messages:
                message = self.voice_messages[message_type]
            else:
                raise gcmd.error("No MESSAGE specified and TYPE '%s' not found" % message_type)
        
        # === Volume Override Handling ===
        # Temporarily adjust volume if specified
        original_volume = self.volume
        if volume != self.volume:
            self.volume = volume
        
        # === Execute Announcement ===
        success = self._announce_message(message_type, message)
        
        # === Restore Original Settings ===
        self.volume = original_volume
        
        # === User Feedback ===
        if success:
            gcmd.respond_info("Voice announcement sent: %s" % message)
        else:
            gcmd.respond_info("Voice announcement blocked (too frequent or disabled)")
    
    cmd_VOICE_CONFIG_help = "Configure voice settings"
    def cmd_VOICE_CONFIG(self, gcmd):
        """
        G-code command: VOICE_CONFIG
        
        Syntax: VOICE_CONFIG [ENABLE=<0|1>] [VOLUME=<0.0-1.0>] [SPEED=<0.5-2.0>] [LANGUAGE=<lang>]
        
        Parameters:
        - ENABLE: Enable (1) or disable (0) voice announcements
        - VOLUME: Set voice volume (0.0 = mute, 1.0 = maximum)
        - SPEED: Set voice speed (0.5 = slow, 2.0 = fast)
        - LANGUAGE: Set voice language code (en, zh, es, etc.)
        
        Examples:
        - VOICE_CONFIG ENABLE=1 VOLUME=0.8
        - VOICE_CONFIG SPEED=1.2 LANGUAGE=en
        - VOICE_CONFIG (shows current settings)
        """
        changed = []
        
        # === Enable/Disable Setting ===
        if gcmd.get('ENABLE', None) is not None:
            self.enabled = gcmd.get_int('ENABLE', self.enabled, minval=0, maxval=1) == 1
            changed.append("enabled=%s" % self.enabled)
        
        # === Volume Setting ===
        if gcmd.get('VOLUME', None) is not None:
            self.volume = gcmd.get_float('VOLUME', self.volume, minval=0.0, maxval=1.0)
            changed.append("volume=%.1f" % self.volume)
        
        # === Speed Setting ===
        if gcmd.get('SPEED', None) is not None:
            self.voice_speed = gcmd.get_float('SPEED', self.voice_speed, minval=0.5, maxval=2.0)
            changed.append("speed=%.1f" % self.voice_speed)
        
        # === Language Setting ===
        if gcmd.get('LANGUAGE', None) is not None:
            self.language = gcmd.get('LANGUAGE', self.language)
            changed.append("language=%s" % self.language)
        
        # === User Feedback ===
        if changed:
            gcmd.respond_info("Voice config updated: %s" % ", ".join(changed))
            self.logger.info("Voice config updated: %s", ", ".join(changed))
        else:
            # Show current settings if no parameters provided
            gcmd.respond_info("Voice config - enabled: %s, volume: %.1f, speed: %.1f, language: %s" % 
                            (self.enabled, self.volume, self.voice_speed, self.language))
    
    cmd_VOICE_STATUS_help = "Show voice plugin status"
    def cmd_VOICE_STATUS(self, gcmd):
        """
        G-code command: VOICE_STATUS
        
        Syntax: VOICE_STATUS
        
        Shows detailed status information about the voice plugin including:
        - Current configuration settings
        - Last announcement details
        - Queue status
        
        No parameters required.
        """
        # === Status Information Collection ===
        status_info = [
            "Voice Plugin Status:",
            "  Enabled: %s" % self.enabled,
            "  Volume: %.1f" % self.volume,
            "  Speed: %.1f" % self.voice_speed,
            "  Language: %s" % self.language,
            "  Audio Player: %s" % (self.selected_player or "None"),
            "  Supported Formats: %s" % ", ".join(self.supported_formats),
            "  Last announcement: %s" % (self.last_announcement or "None"),
            "  Queue length: %d" % len(self.announcement_queue)
        ]
        
        # === Send Status to User ===
        gcmd.respond_info("\n".join(status_info))
    
    cmd_VOICE_TEST_help = "Test voice functionality"
    def cmd_VOICE_TEST(self, gcmd):
        """
        G-code command: VOICE_TEST
        
        Syntax: VOICE_TEST [TYPE=<message_type>]
        
        Parameters:
        - TYPE: Message type to test (optional, default: 'ready')
        
        Tests voice functionality by playing a predefined message.
        Available types: print_start, print_end, print_pause, print_resume,
        print_cancel, filament_runout, error, ready, heating, temp_reached
        
        Examples:
        - VOICE_TEST (tests 'ready' message)
        - VOICE_TEST TYPE=print_start
        """
        # === Parameter Extraction ===
        test_type = gcmd.get('TYPE', 'ready')
        
        # === Test Execution ===
        if test_type in self.voice_messages:
            success = self._announce_message(test_type)
            if success:
                gcmd.respond_info("Voice test completed: %s" % test_type)
            else:
                gcmd.respond_info("Voice test blocked (disabled or too frequent)")
        else:
            # === Error Handling ===
            available_types = ", ".join(self.voice_messages.keys())
            raise gcmd.error("Unknown test type '%s'. Available: %s" % (test_type, available_types))
    
    cmd_VOICE_SCAN_help = "Scan for audio files and rebuild cache"
    def cmd_VOICE_SCAN(self, gcmd):
        """
        G-code command: VOICE_SCAN
        
        Syntax: VOICE_SCAN
        
        Scans the audio directory for available audio files and rebuilds
        the internal cache. Use this command after adding new audio files.
        
        No parameters required.
        """
        # === Rescan Audio Files ===
        self.logger.info("Rescanning audio files...")
        self._scan_audio_files()
        
        # === Report Results ===
        total_files = 0
        for msg_type in self.audio_file_cache.values():
            for lang_files in msg_type.values():
                total_files += len(lang_files)
        
        message_types = list(self.audio_file_cache.keys())
        
        gcmd.respond_info("Audio file scan completed:")
        gcmd.respond_info("  Audio Player: %s" % (self.selected_player or "None"))
        gcmd.respond_info("  Found %d audio files" % total_files)
        gcmd.respond_info("  Supported Formats: %s" % ", ".join(self.supported_formats))
        gcmd.respond_info("  Available message types: %s" % ", ".join(message_types))
        
        # === Show Missing Files ===
        missing_types = []
        for msg_type in self.voice_messages.keys():
            if msg_type not in self.audio_file_cache:
                missing_types.append(msg_type)
        
        if missing_types:
            gcmd.respond_info("  Missing audio files for: %s" % ", ".join(missing_types))
        else:
            gcmd.respond_info("  All message types have audio files available")


def load_config(config):
    """
    Plugin entry point - called by Klipper to load the plugin.
    
    Args:
        config: Configuration object for this plugin section
        
    Returns:
        KlipperVoice: Plugin instance
        
    This function is required by Klipper's plugin system.
    It must be named 'load_config' and return the plugin instance.
    """
    return KlipperVoice(config)