import os
import subprocess
import numpy as np
import soundfile as sf
from scipy.signal import butter, filtfilt
try:
    from openvino_noise_suppression import OpenVINONoiseSuppressor
    AI_SUPPRESSOR = OpenVINONoiseSuppressor()
except ImportError as e:
    AI_SUPPRESSOR = None
    print(f"Warning: {e}. AI noise suppression will be unavailable.")

# Default parameters
DEFAULT_ALPHA = 0.97
DEFAULT_ORDER = 4

def apply_audio_filter(filter_name, input_path, output_path,
                       alpha=DEFAULT_ALPHA, order=DEFAULT_ORDER):
    """
    Dispatches to the requested audio filter.
    Supported filters: 'voice_enhancement', 'ai_noise_suppression'
    """
    if filter_name == 'voice_enhancement':
        return _apply_voice_enhancement(input_path, output_path, alpha, order)
    if filter_name == 'ai_noise_suppression':
        return _apply_ai_noise_suppression(input_path, output_path)
    return False, f'Unsupported filter: {filter_name}'

def _apply_voice_enhancement(input_path, output_path, alpha, order):
    """
    1) Extracts WAV from video
    2) Applies pre-emphasis + Butterworth band-pass (800–6000 Hz)
    3) Remuxes processed audio into video
    """
    wd = os.path.dirname(output_path) or '.'
    wav1 = os.path.join(wd, 'extracted.wav')
    wav2 = os.path.join(wd, 'processed.wav')
    try:
        # Extract raw PCM WAV
        subprocess.run([
            'ffmpeg','-y','-i', input_path,
            '-vn','-acodec','pcm_s16le','-ar','44100','-ac','2', wav1
        ], check=True, capture_output=True)

        audio, sr = sf.read(wav1)
        # Apply filter per channel
        if audio.ndim > 1:
            out = np.zeros_like(audio)
            for ch in range(audio.shape[1]):
                out[:,ch] = _voice_filter(audio[:,ch], sr, alpha, order)
        else:
            out = _voice_filter(audio, sr, alpha, order)

        sf.write(wav2, out, sr)

        # Remux cleaned audio into video
        subprocess.run([
            'ffmpeg','-y','-i', input_path, '-i', wav2,
            '-c:v','copy','-c:a','aac','-map','0:v','-map','1:a',
            output_path
        ], check=True, capture_output=True)

        return True, 'Voice enhancement applied successfully'

    except Exception as e:
        return False, str(e)

    finally:
        for f in (wav1, wav2):
            if os.path.exists(f):
                os.remove(f)

def _voice_filter(x, sr, alpha, order):
    """Pre-emphasis followed by 4th-order Butterworth band-pass."""
    # Pre-emphasis
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = x[i] - alpha * x[i-1]

    # Butterworth band-pass 800–6000 Hz
    ny = sr / 2.0
    low, high = max(1e-3, 800/ny), min(0.999, 6000/ny)
    if low >= high:
        high = low + 1e-3
    b, a = butter(order, [low, high], btype='band')

    filtered = filtfilt(b, a, y)
    return filtered
def _apply_ai_noise_suppression(input_path, output_path):
    """
    Uses the Ambassador-exclusive OpenVINO DenseUNet model for noise suppression:
    1) Extracts 16 kHz mono WAV
    2) Runs AI suppressor
    3) Remuxes cleaned audio into video
    """
    if AI_SUPPRESSOR is None:
        return False, "OpenVINONoiseSuppressor is not available. Please install the required module."
    wd = os.path.dirname(output_path) or '.'
    wav_in  = os.path.join(wd, 'ai_extracted.wav')
    wav_out = os.path.join(wd, 'ai_processed.wav')
    try:
        # Extract mono 16 kHz WAV
        subprocess.run([
            'ffmpeg','-y','-i', input_path,
            '-vn','-acodec','pcm_s16le','-ar','16000','-ac','1', wav_in
        ], check=True, capture_output=True)

        # Run OpenVINO noise suppressor
        AI_SUPPRESSOR.suppress_file(wav_in, wav_out)

        # Remux cleaned audio
        subprocess.run([
            'ffmpeg','-y','-i', input_path, '-i', wav_out,
            '-c:v','copy','-c:a','aac','-map','0:v','-map','1:a',
            output_path
        ], check=True, capture_output=True)

        return True, 'AI noise suppression applied successfully'

    except Exception as e:
        return False, str(e)

    finally:
        for f in (wav_in, wav_out):
            if os.path.exists(f):
                os.remove(f)
            if os.path.exists(f):
                os.remove(f)
