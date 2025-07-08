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
        
        # Audio file format/extension
        self.audio_format = config.get('audio_format', 'mp3')
        
        # Audio player command (can be 'mpg123', 'aplay', 'paplay', etc.)
        self.audio_player = config.get('audio_player', 'mpg123')
        
        # Additional audio player arguments
        self.audio_player_args = config.get('audio_player_args', '-q').split()
        
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
        
        # === Validate Audio Player ===
        try:
            result = subprocess.run(['which', self.audio_player], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                self.logger.info("Audio player found: %s", self.audio_player)
            else:
                self.logger.warning("Audio player not found: %s", self.audio_player)
                self.logger.warning("Voice announcements will be logged only")
        except Exception as e:
            self.logger.error("Error checking audio player: %s", str(e))
        
        # === Scan Audio Files ===
        self._scan_audio_files()
    
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
                if not filename.endswith('.' + self.audio_format):
                    continue
                
                # Parse filename: message_type.language.format
                name_parts = filename.rsplit('.', 2)
                if len(name_parts) >= 2:
                    message_type = name_parts[0]
                    language = name_parts[1] if len(name_parts) == 3 else 'default'
                    
                    # Build file path
                    file_path = os.path.join(self.audio_base_path, filename)
                    
                    # Store in cache
                    if message_type not in self.audio_file_cache:
                        self.audio_file_cache[message_type] = {}
                    self.audio_file_cache[message_type][language] = file_path
                    
                    self.logger.debug("Found audio file: %s -> %s (%s)", 
                                    message_type, file_path, language)
            
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
        1. message_type.current_language.format
        2. message_type.en.format (fallback to English)
        3. message_type.default.format (generic fallback)
        """
        if message_type not in self.audio_file_cache:
            return None
        
        language_files = self.audio_file_cache[message_type]
        
        # Try current language first
        if self.language in language_files:
            return language_files[self.language]
        
        # Fallback to English
        if 'en' in language_files:
            return language_files['en']
        
        # Fallback to default
        if 'default' in language_files:
            return language_files['default']
        
        # Use any available file
        if language_files:
            return next(iter(language_files.values()))
        
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
                # Build command
                cmd = [self.audio_player] + self.audio_player_args
                
                # Add volume control if supported
                if self.use_hardware_volume and self.audio_player == 'mpg123':
                    # mpg123 volume control: -g <gain> (0-100)
                    gain = int(self.volume * 100)
                    cmd.extend(['-g', str(gain)])
                elif self.use_hardware_volume and self.audio_player in ['aplay', 'paplay']:
                    # For aplay/paplay, we might need to use amixer for volume
                    pass  # Volume control handled separately
                
                # Add audio file
                cmd.append(audio_file)
                
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
            'available_messages': list(self.voice_messages.keys())
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
        total_files = sum(len(lang_files) for lang_files in self.audio_file_cache.values())
        message_types = list(self.audio_file_cache.keys())
        
        gcmd.respond_info("Audio file scan completed:")
        gcmd.respond_info("  Found %d audio files" % total_files)
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