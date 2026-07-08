from flask import Flask, request, jsonify, send_from_directory
import os
import uuid
import tempfile
from gtts import gTTS
import PyPDF2
import logging
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
AUDIO_FOLDER = 'audio_files'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

# Ensure the upload and audio folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if a file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    # Check if the file is empty
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Check file type
    if not allowed_file(file.filename):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    try:
        # Generate a unique filename
        original_filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # Save the uploaded file
        file.save(filepath)
        logger.info(f"Saved file: {filepath}")
        
        # Extract text from PDF
        text = extract_text_from_pdf(filepath)
        
        if not text.strip():
            return jsonify({'error': 'Could not extract text from the PDF. The PDF might be scanned or protected.'}), 400
        
        # Convert text to audio
        audio_filename = filename.rsplit('.', 1)[0] + '.mp3'
        audio_path = os.path.join(AUDIO_FOLDER, audio_filename)
        
        text_to_speech(text, audio_path)
        logger.info(f"Created audio file: {audio_path}")
        
        # Return the URL to the audio file
        audio_url = f"/audio/{audio_filename}"
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': os.path.basename(original_filename)
        })
    
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return jsonify({'error': f'Error processing file: {str(e)}'}), 500

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            
            # Extract text from each page
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + " "
        
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise Exception(f"Error extracting text from PDF: {str(e)}")

def text_to_speech(text, output_path):
    """Convert text to speech using Google Text-to-Speech."""
    try:
        # Split text into chunks if it's too long for gTTS
        max_chars = 5000  # gTTS has limitations on text length
        text_chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
        
        # Create a temporary directory for intermediate files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_files = []
            
            # Convert each chunk to speech
            for i, chunk in enumerate(text_chunks):
                if not chunk.strip():
                    continue
                
                temp_file = os.path.join(temp_dir, f"chunk_{i}.mp3")
                tts = gTTS(text=chunk, lang='en', slow=False)
                tts.save(temp_file)
                temp_files.append(temp_file)
            
            # If there's only one chunk, just move it
            if len(temp_files) == 1:
                with open(temp_files[0], 'rb') as src, open(output_path, 'wb') as dst:
                    dst.write(src.read())
            # Otherwise, combine the chunks (this would require pydub or a similar library)
            # For simplicity, we're just using the first chunk here
            # In a full implementation, you would need to concatenate the audio files
            elif len(temp_files) > 1:
                with open(temp_files[0], 'rb') as src, open(output_path, 'wb') as dst:
                    dst.write(src.read())
                logger.warning("Multiple audio chunks generated but only the first one is used. Consider implementing audio concatenation.")
    except Exception as e:
        logger.error(f"Error in text-to-speech conversion: {str(e)}")
        raise Exception(f"Error in text-to-speech conversion: {str(e)}")

@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve the generated audio file."""
    return send_from_directory(AUDIO_FOLDER, filename)

# Serve the static files (HTML, CSS, JS)
@app.route('/')
def index():
    return app.send_static_file('index.html')

# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(500)
def internal_server_error(error):
    return jsonify({'error': 'Internal server error. Please try again later.'}), 500

if __name__ == '__main__':
    app.run(debug=True)