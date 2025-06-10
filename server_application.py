from flask import Flask, request, jsonify, send_file, render_template
import os

# One dispatcher for audio—and it knows about AI or voice filters
from audio_filter import apply_audio_filter

# Video filters dispatcher
from video_filter import apply_video_filter

app = Flask(__name__)
UPLOAD_FOLDER    = 'uploads'
PROCESSED_FOLDER = 'processed'
os.makedirs(UPLOAD_FOLDER,    exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

VIDEO_PATH  = os.path.join(UPLOAD_FOLDER,    'input.mp4')
OUTPUT_PATH = os.path.join(PROCESSED_FOLDER, 'output.mp4')

# Only one filter at a time
CURRENT_FILTER = None

@app.route('/')
def index():
    return render_template('project_template.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['video']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    # Clear old files
    for p in (VIDEO_PATH, OUTPUT_PATH):
        if os.path.exists(p):
            os.remove(p)

    try:
        file.save(VIDEO_PATH)
        return jsonify({'message': 'Video uploaded successfully'}), 200
    except Exception as e:
        return jsonify({'error': f'Upload failed: {e}'}), 500

@app.route('/delete', methods=['DELETE'])
def delete():
    global CURRENT_FILTER
    try:
        for p in (VIDEO_PATH, OUTPUT_PATH):
            if os.path.exists(p):
                os.remove(p)
        CURRENT_FILTER = None
        return jsonify({'message': 'Video deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': f'Delete failed: {e}'}), 500

@app.route('/configure', methods=['POST'])
def configure():
    global CURRENT_FILTER
    try:
        data = request.get_json()
        name = data.get('filter')
        available = ['ai_noise_suppression', 'voice_enhancement', 'grayscale']
        if name not in available:
            return jsonify({'error': f'Invalid filter. Choose from {available}'}), 400
        CURRENT_FILTER = name
        return jsonify({'message': f'Filter set to: {name}'}), 200
    except Exception as e:
        return jsonify({'error': f'Configuration failed: {e}'}), 500

@app.route('/apply', methods=['POST'])
def apply():
    if not os.path.exists(VIDEO_PATH):
        return jsonify({'error': 'No video uploaded'}), 400
    if not CURRENT_FILTER:
        return jsonify({'error': 'No filter configured'}), 400

    # Remove old output
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)

    try:
        inp = os.path.abspath(VIDEO_PATH)
        out = os.path.abspath(OUTPUT_PATH)

        if CURRENT_FILTER in ('ai_noise_suppression','voice_enhancement'):
            # alpha and order only used by voice_enhancement; defaults inside apply_audio_filter
            success, msg = apply_audio_filter(CURRENT_FILTER, inp, out)
        elif CURRENT_FILTER == 'grayscale':
            success, msg = apply_video_filter('grayscale', inp, out)
        else:
            return jsonify({'error': 'Unknown filter configured'}), 400

        if not success:
            return jsonify({'error': msg}), 500
        return jsonify({'message': msg}), 200

    except Exception as e:
        return jsonify({'error': f'Processing failed: {e}'}), 500

@app.route('/stream', methods=['GET'])
def stream():
    # Serve processed if exists, otherwise original
    if os.path.exists(OUTPUT_PATH):
        return send_file(OUTPUT_PATH, mimetype='video/mp4', conditional=True)
    if os.path.exists(VIDEO_PATH):
        return send_file(VIDEO_PATH,  mimetype='video/mp4', conditional=True)
    return jsonify({'error': 'No video available'}), 404

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'uploaded': os.path.exists(VIDEO_PATH),
        'processed': os.path.exists(OUTPUT_PATH),
        'filter': CURRENT_FILTER,
        'available': ['ai_noise_suppression','voice_enhancement','grayscale']
    })

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

if __name__ == '__main__':
    app.run(debug=True, port=5000)
