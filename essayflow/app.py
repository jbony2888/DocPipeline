"""
Essay Contest Processor (Prototype)

A modular pipeline for processing handwritten essay submissions.

Setup:
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
    pip install -r requirements.txt
    streamlit run app.py

This prototype uses stub OCR. Real OCR providers can be integrated later.
"""

import streamlit as st
from pathlib import Path

from pipeline.ingest import ingest_upload
from pipeline.runner import process_submission
from pipeline.csv_writer import append_to_csv, get_csv_stats


# Page config
st.set_page_config(
    page_title="Essay Contest Processor",
    page_icon="📝",
    layout="wide"
)

# Title and description
st.title("📝 Essay Contest Processor (Prototype)")
st.markdown("""
Process single-page handwritten essay contest submissions.  
Extracts contact info, computes metrics, and validates data.
""")

st.divider()

# Initialize session state
if "processed_record" not in st.session_state:
    st.session_state.processed_record = None
if "processing_report" not in st.session_state:
    st.session_state.processing_report = None
if "csv_written" not in st.session_state:
    st.session_state.csv_written = False

# File upload section
st.subheader("1️⃣ Upload Submission")

uploaded_file = st.file_uploader(
    "Choose an image file",
    type=["png", "jpg", "jpeg", "pdf"],
    help="Upload a single-page handwritten essay submission"
)

# OCR provider selection
ocr_provider = st.selectbox(
    "OCR Provider",
    options=["stub"],
    index=0,
    help="Currently only stub OCR is available (simulates handwritten text)"
)

# Process button
if uploaded_file is not None:
    col1, col2 = st.columns([1, 4])
    
    with col1:
        process_btn = st.button("🚀 Run Processor", type="primary", use_container_width=True)
    
    if process_btn:
        with st.spinner("Processing submission..."):
            # Ingest the upload
            file_bytes = uploaded_file.read()
            ingest_data = ingest_upload(
                uploaded_bytes=file_bytes,
                original_filename=uploaded_file.name,
                base_artifacts_dir="artifacts"
            )
            
            # Run the pipeline
            record, report = process_submission(
                image_path=ingest_data["saved_path"],
                submission_id=ingest_data["submission_id"],
                artifact_dir=ingest_data["artifact_dir"],
                ocr_provider_name=ocr_provider
            )
            
            # Store in session state
            st.session_state.processed_record = record
            st.session_state.processing_report = report
            st.session_state.csv_written = False
            
        st.success("✅ Processing complete!")

# Display results
if st.session_state.processed_record is not None:
    st.divider()
    st.subheader("2️⃣ Extracted Data")
    
    record = st.session_state.processed_record
    report = st.session_state.processing_report
    
    # Contact information
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📋 Contact Information**")
        st.text(f"Submission ID: {record.submission_id}")
        st.text(f"Student Name: {record.student_name or '(not found)'}")
        st.text(f"School: {record.school_name or '(not found)'}")
        st.text(f"Grade: {record.grade if record.grade else '(not found)'}")
        if record.teacher_name:
            st.text(f"Teacher: {record.teacher_name}")
        if record.city_or_location:
            st.text(f"Location: {record.city_or_location}")
    
    with col2:
        st.markdown("**📊 Essay Metrics**")
        st.text(f"Word Count: {record.word_count}")
        if record.ocr_confidence_avg:
            st.text(f"OCR Confidence: {record.ocr_confidence_avg:.2%}")
        
        # Validation status
        if record.needs_review:
            st.warning(f"⚠️ Needs Review: {record.review_reason_codes}")
        else:
            st.success("✅ Ready for submission")
    
    # Artifacts info
    with st.expander("🗂️ Artifact Details"):
        st.text(f"Artifact Directory: {record.artifact_dir}")
        st.markdown("**Generated Files:**")
        artifact_files = [
            "original.[ext]",
            "ocr.json",
            "raw_text.txt",
            "contact_block.txt",
            "essay_block.txt",
            "structured.json",
            "validation.json"
        ]
        for filename in artifact_files:
            st.text(f"  • {filename}")
    
    # Processing report
    with st.expander("📈 Processing Report"):
        st.json(report)
    
    # CSV export section
    st.divider()
    st.subheader("3️⃣ Export to CSV")
    
    col1, col2 = st.columns([1, 4])
    
    with col1:
        write_csv_btn = st.button(
            "💾 Write to CSV",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.csv_written
        )
    
    if write_csv_btn:
        csv_path = append_to_csv(record, output_dir="outputs")
        st.session_state.csv_written = True
        
        # Show which file was written
        filename = Path(csv_path).name
        st.success(f"✅ Record written to: `{filename}`")
    
    # Show CSV statistics
    stats = get_csv_stats(output_dir="outputs")
    
    st.markdown("**📁 CSV File Status:**")
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Clean Records", stats["clean_count"])
        if stats["clean_count"] > 0:
            st.caption(f"`{Path(stats['clean_file']).name}`")
    
    with col2:
        st.metric("Needs Review", stats["needs_review_count"])
        if stats["needs_review_count"] > 0:
            st.caption(f"`{Path(stats['needs_review_file']).name}`")

# Footer
st.divider()
st.caption("⚠️ This is a prototype using stub OCR. Real OCR integration coming soon.")

