import streamlit as st
import requests
import os
import time
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini API
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("GEMINI_API_KEY not found in .env file. Please add it.")
    st.stop()

BASE_URL = "https://generativelanguage.googleapis.com"

# Initialize session state
if "file_uri" not in st.session_state:
    st.session_state.file_uri = None
if "file_name" not in st.session_state:
    st.session_state.file_name = None
if "upload_complete" not in st.session_state:
    st.session_state.upload_complete = False

st.title("CCTV Video Analysis with Gemini")

uploaded_file = st.file_uploader("Upload a video file", type=["mp4", "mov", "avi", "webm"])

if uploaded_file is not None:
    # Save the uploaded file temporarily
    temp_file_path = "temp_video.mp4"
    with open(temp_file_path, "wb") as f:
        f.write(uploaded_file.read())

    st.video(temp_file_path)

    # Upload Button
    if st.button("Upload & Process Video"):
        with st.spinner("Uploading video to Gemini..."):
            try:
                file_size = os.path.getsize(temp_file_path)
                headers = {
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(file_size),
                    "X-Goog-Upload-Header-Content-Type": "video/mp4",
                    "Content-Type": "application/json"
                }
                upload_url_response = requests.post(
                    f"{BASE_URL}/upload/v1beta/files?key={api_key}",
                    headers=headers,
                    json={"file": {"display_name": uploaded_file.name}}
                )
                upload_url_response.raise_for_status()
                upload_url = upload_url_response.headers["X-Goog-Upload-URL"]

                with open(temp_file_path, "rb") as f:
                    upload_response = requests.post(
                        upload_url,
                        headers={
                            "Content-Length": str(file_size),
                            "X-Goog-Upload-Offset": "0",
                            "X-Goog-Upload-Command": "upload, finalize"
                        },
                        data=f
                    )
                upload_response.raise_for_status()
                file_info = upload_response.json()
                st.session_state.file_uri = file_info["file"]["uri"]
                st.session_state.file_name = file_info["file"]["name"]
                st.info(f"Upload complete: {st.session_state.file_uri}")
                
            except Exception as e:
                st.error(f"Failed to upload video: {e}")
                st.stop()

        # Poll for Processing
        with st.spinner("Processing video..."):
            state = "PROCESSING"
            while state == "PROCESSING":
                time.sleep(2)
                try:
                    get_response = requests.get(f"{BASE_URL}/v1beta/{st.session_state.file_name}?key={api_key}")
                    get_response.raise_for_status()
                    file_data = get_response.json()
                    if "file" in file_data:
                        state = file_data["file"]["state"]
                    else:
                        state = file_data["state"]
                except Exception as e:
                    st.error(f"Failed to check file status: {e}")
                    st.stop()

            if state == "FAILED":
                st.error("Video processing failed.")
                st.stop()
            
            st.session_state.upload_complete = True
            st.success("Video processing complete. Ready for analysis.")

# Analysis Section
if st.session_state.upload_complete:
    st.divider()
    st.subheader("Analysis Options")
    
    analysis_type = st.selectbox(
        "Choose Analysis Type",
        ["Anomaly Detection", "Object Detection", "Unknown Person Detection", "Summarization"]
    )

    prompt_text = ""
    
    if analysis_type == "Anomaly Detection":
        prompt_text = (
            "Analyze the video for any anomalies, unusual events, or safety hazards. "
            "Return a JSON list of events with the following schema: "
            "[{'timestamp': 'MM:SS', 'description': 'string', 'severity': 'low/medium/high'}]"
        )
    elif analysis_type == "Object Detection":
        prompt_text = (
            "Detect the main objects (cars, people, bags, etc.) in the video. "
            "Return a JSON list with the following schema: "
            "[{'object_name': 'string', 'count': int, 'timestamps': ['MM:SS', ...]}]"
        )
    elif analysis_type == "Unknown Person Detection":
        prompt_text = (
            "Identify individuals in the video. Flag any that appear to be unauthorized, suspicious, or unknown "
            "(based on general context, e.g., loitering, hiding face). "
            "Return a JSON list with: "
            "[{'timestamp': 'MM:SS', 'description': 'string', 'suspicion_level': 'low/medium/high'}]"
        )
    elif analysis_type == "Summarization":
        focus_points = st.text_input("Focus Points (Optional)", key="focus_input")
        prompt_text = (
            "Summarize this video. Return a JSON object with: "
            "{'summary': 'string', 'key_events': [{'timestamp': 'MM:SS', 'event': 'string'}]}"
        )
        if focus_points:
            prompt_text += f" Focus the summary only on: {focus_points}"

    if st.button("Run Analysis"):
        with st.spinner(f"Running {analysis_type}..."):
            try:
                model_name = "gemini-2.5-flash"
                url = f"{BASE_URL}/v1beta/models/{model_name}:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [
                            {"file_data": {"mime_type": "video/mp4", "file_uri": st.session_state.file_uri}},
                            {"text": prompt_text}
                        ]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                
                response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload)
                response.raise_for_status()
                result = response.json()
                
                try:
                    response_text = result["candidates"][0]["content"]["parts"][0]["text"]
                    # Parse JSON to ensure it's valid and pretty print
                    json_data = json.loads(response_text)
                    st.subheader(f"{analysis_type} Results")
                    st.json(json_data)
                except (KeyError, json.JSONDecodeError) as e:
                    st.error(f"Failed to parse response: {e}")
                    st.warning("Raw Response:")
                    st.text(result)

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                if 'response' in locals():
                     st.error(f"Response details: {response.text}")

    # Cleanup temp file (optional)
    # os.remove(temp_file_path)
