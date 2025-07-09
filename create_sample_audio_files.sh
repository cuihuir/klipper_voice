#!/bin/bash

# Klipper Voice Plugin - Sample Audio File Generator
# This script creates sample audio files using text-to-speech (TTS)
# for testing the voice plugin functionality.

# Configuration
AUDIO_DIR="/home/pi/printer_data/voice"
LANGUAGE="en"
FORMAT="mp3"  # Can be: mp3, wav, ogg, flac

# Text-to-speech command (you may need to install espeak or festival)
# Options:
# - espeak: Simple TTS engine
# - festival: More advanced TTS engine
# - pico2wave: Compact TTS engine
# - Online services (requires internet)

TTS_ENGINE="espeak"  # Change to your preferred TTS engine

# Auto-detect ffmpeg for format conversion
FFMPEG_AVAILABLE=false
if command -v ffmpeg &> /dev/null; then
    FFMPEG_AVAILABLE=true
fi

# Create audio directory
echo "Creating audio directory: $AUDIO_DIR"
mkdir -p "$AUDIO_DIR"

# Check if TTS engine is available
check_tts_engine() {
    if ! command -v $TTS_ENGINE &> /dev/null; then
        echo "Error: $TTS_ENGINE is not installed."
        echo "Please install it using one of the following commands:"
        echo "  sudo apt install espeak espeak-data"
        echo "  sudo apt install festival"
        echo "  sudo apt install libttspico-utils"
        exit 1
    fi
}

# Generate audio file using espeak
generate_espeak() {
    local message="$1"
    local filename="$2"
    echo "Generating: $filename"
    espeak -s 150 -v en "$message" -w "/tmp/temp.wav"
    
    # Convert to requested format
    convert_audio_format "/tmp/temp.wav" "$AUDIO_DIR/$filename"
    rm -f "/tmp/temp.wav"
}

# Generate audio file using festival
generate_festival() {
    local message="$1"
    local filename="$2"
    echo "Generating: $filename"
    echo "$message" | festival --tts --pipe > "/tmp/temp.wav"
    
    # Convert to requested format
    convert_audio_format "/tmp/temp.wav" "$AUDIO_DIR/$filename"
    rm -f "/tmp/temp.wav"
}

# Generate audio file using pico2wave
generate_pico2wave() {
    local message="$1"
    local filename="$2"
    echo "Generating: $filename"
    pico2wave -l en-US -w "/tmp/temp.wav" "$message"
    
    # Convert to requested format
    convert_audio_format "/tmp/temp.wav" "$AUDIO_DIR/$filename"
    rm -f "/tmp/temp.wav"
}

# Convert audio format using ffmpeg or fallback methods
convert_audio_format() {
    local input_file="$1"
    local output_file="$2"
    local output_format="${output_file##*.}"
    
    if [[ "$output_format" == "wav" ]]; then
        # For WAV, just copy the file
        cp "$input_file" "$output_file"
    elif [[ "$FFMPEG_AVAILABLE" == true ]]; then
        # Use ffmpeg for conversion (supports all formats)
        ffmpeg -i "$input_file" -acodec pcm_s16le -ar 44100 -ac 2 "$output_file" -y -v quiet
    else
        # Fallback based on available tools
        case "$output_format" in
            "mp3")
                if command -v lame &> /dev/null; then
                    lame -b 128 "$input_file" "$output_file"
                else
                    echo "Warning: lame not found, saving as WAV instead of MP3"
                    cp "$input_file" "${output_file%.mp3}.wav"
                fi
                ;;
            "ogg")
                if command -v oggenc &> /dev/null; then
                    oggenc -o "$output_file" "$input_file"
                else
                    echo "Warning: oggenc not found, saving as WAV instead of OGG"
                    cp "$input_file" "${output_file%.ogg}.wav"
                fi
                ;;
            "flac")
                if command -v flac &> /dev/null; then
                    flac -o "$output_file" "$input_file"
                else
                    echo "Warning: flac not found, saving as WAV instead of FLAC"
                    cp "$input_file" "${output_file%.flac}.wav"
                fi
                ;;
            *)
                echo "Warning: Unsupported format $output_format, saving as WAV"
                cp "$input_file" "${output_file%.*}.wav"
                ;;
        esac
    fi
}

# Main generation function
generate_audio() {
    local message="$1"
    local message_type="$2"
    local filename="${message_type}.${LANGUAGE}.${FORMAT}"
    
    case $TTS_ENGINE in
        "espeak")
            generate_espeak "$message" "$filename"
            ;;
        "festival")
            generate_festival "$message" "$filename"
            ;;
        "pico2wave")
            generate_pico2wave "$message" "$filename"
            ;;
        *)
            echo "Error: Unknown TTS engine: $TTS_ENGINE"
            exit 1
            ;;
    esac
}

# Check dependencies
check_tts_engine

echo "Starting audio file generation..."
echo "TTS Engine: $TTS_ENGINE"
echo "Language: $LANGUAGE"
echo "Format: $FORMAT"
echo "Output directory: $AUDIO_DIR"
echo ""

# Generate all the audio files
generate_audio "Print started, please stand by" "print_start"
generate_audio "Print completed successfully" "print_end"
generate_audio "Print has been paused" "print_pause"
generate_audio "Print resumed" "print_resume"
generate_audio "Print cancelled" "print_cancel"
generate_audio "Filament runout detected, please reload filament" "filament_runout"
generate_audio "Error occurred, please check the printer" "error"
generate_audio "Printer is ready for operation" "ready"
generate_audio "Heating in progress" "heating"
generate_audio "Target temperature reached" "temp_reached"

echo ""
echo "Audio file generation completed!"
echo "Generated files in: $AUDIO_DIR"
echo ""
echo "To test the audio files, you can use:"
echo "  mpg123 $AUDIO_DIR/print_start.$LANGUAGE.$FORMAT"
echo "  aplay $AUDIO_DIR/ready.$LANGUAGE.wav"
echo ""
echo "In Klipper, test with:"
echo "  VOICE_SCAN"
echo "  VOICE_TEST TYPE=ready"
echo "  VOICE_ANNOUNCE TYPE=print_start"
echo ""

# List generated files
echo "Generated files:"
ls -la "$AUDIO_DIR"

# Install instructions
echo ""
echo "If you need to install dependencies:"
echo ""
echo "For espeak:"
echo "  sudo apt update"
echo "  sudo apt install espeak espeak-data"
echo ""
echo "For festival:"
echo "  sudo apt update"
echo "  sudo apt install festival"
echo ""
echo "For pico2wave:"
echo "  sudo apt update"
echo "  sudo apt install libttspico-utils"
echo ""
echo "For audio format conversion (ffmpeg - recommended):"
echo "  sudo apt install ffmpeg"
echo ""
echo "For MP3 encoding (lame):"
echo "  sudo apt install lame"
echo ""
echo "For OGG encoding (vorbis-tools):"
echo "  sudo apt install vorbis-tools"
echo ""
echo "For FLAC encoding (flac):"
echo "  sudo apt install flac"
echo ""
echo "For audio playback (choose one):"
echo "  sudo apt install ffmpeg          # Best option - plays all formats"
echo "  sudo apt install mpg123          # For MP3 playback"
echo "  sudo apt install pulseaudio-utils # For PulseAudio (paplay)"
echo "  sudo apt install vlc              # For VLC (cvlc)"