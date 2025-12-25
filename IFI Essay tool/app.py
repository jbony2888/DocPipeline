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
import json
from pathlib import Path

from pipeline.ingest import ingest_upload
from pipeline.runner import process_submission
from pipeline.csv_writer import (
    append_to_csv, 
    get_csv_stats, 
    load_records_from_csv,
    update_record_in_csv,
    move_record_between_csvs
)
from pipeline.schema import SubmissionRecord
from pipeline.database import (
    init_database,
    save_record,
    get_records as get_db_records,
    get_record_by_id,
    update_record as update_db_record,
    delete_record as delete_db_record,
    get_stats as get_db_stats
)


def format_review_reasons(reason_codes: str) -> str:
    """Convert review reason codes into human-readable format."""
    if not reason_codes:
        return "Pending review"
    
    # Map codes to readable labels
    reason_map = {
        "MISSING_STUDENT_NAME": "Missing Student Name",
        "MISSING_SCHOOL_NAME": "Missing School Name",
        "MISSING_GRADE": "Missing Grade",
        "EMPTY_ESSAY": "Empty Essay",
        "SHORT_ESSAY": "Short Essay (< 50 words)",
        "LOW_CONFIDENCE": "Low OCR Confidence",
        "PENDING_REVIEW": "Pending Manual Review"
    }
    
    # Split by semicolon and map each code
    codes = reason_codes.split(";")
    readable_reasons = []
    for code in codes:
        code = code.strip()
        if code:
            readable_reasons.append(reason_map.get(code, code.replace("_", " ").title()))
    
    return " • ".join(readable_reasons) if readable_reasons else "Pending review"


def get_pdf_path(artifact_dir: str) -> Path:
    """Get the path to the original PDF file."""
    artifact_path = Path(artifact_dir)
    
    # Look for original.pdf or original file with any extension
    pdf_path = artifact_path / "original.pdf"
    if pdf_path.exists():
        return pdf_path
    
    # Try to find any file starting with "original"
    for file in artifact_path.glob("original.*"):
        return file
    
    return None


# Page config
st.set_page_config(
    page_title="IFI Essay Gateway",
    page_icon="📝",
    layout="wide"
)

# Ensure required directories exist
Path("artifacts").mkdir(exist_ok=True)
Path("outputs").mkdir(exist_ok=True)

# Initialize database
init_database()

# Title and description
st.title("📝 IFI Essay Gateway")
st.caption("Clearing the way so every fatherhood story is heard.")
st.markdown("""
Welcome to IFI Essay Gateway. This tool helps volunteers and school partners organize essay entries, so more time can be spent reading students' stories about what their fathers and father‑figures mean to them. It automatically gathers basic information from the official entry forms and sorts essays by grade level, while keeping each student's words exactly as they wrote them.
""")

# Processing setup status
import os
groq_key = os.environ.get("GROQ_API_KEY")
google_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_CLOUD_VISION_CREDENTIALS_JSON")

if google_credentials and groq_key:
    st.success("✅ **Ready to Process** - Google Vision and enhanced processing are both configured.", icon="✅")
elif google_credentials:
    st.success("✅ **Ready to Process** - Using Google Vision to read entry forms.", icon="✅")
    st.info("""
    **💡 Tip:** You can optionally add Groq for better handling of handwriting. Contact your administrator if needed.
    """, icon="ℹ️")
elif groq_key:
    st.warning("""
    **⚠️ Setup Required** - Google Vision credentials are needed to read entry forms. Please configure Google Cloud Vision credentials to continue.
    """, icon="⚠️")
else:
    st.warning("""
    **📋 Setup Required**
    
    To process entry forms, you'll need:
    
    **1. Google Vision** (Required - reads text from forms)
    - Contact your administrator for setup instructions
    
    **2. Groq** (Optional - improves handwriting reading)
    - Contact your administrator if you need this enabled
    
    **Note:** All essays must be original student work, unaided by AI, as stated in the contest rules. IFI Essay Gateway never writes, edits, or rewrites essays. It only helps collect information from forms and presents entries in an organized way for our volunteer judges.
    """, icon="📋")

st.divider()

# Initialize session state
if "processed_record" not in st.session_state:
    st.session_state.processed_record = None
if "processing_report" not in st.session_state:
    st.session_state.processing_report = None
if "csv_written" not in st.session_state:
    st.session_state.csv_written = False
if "notifications" not in st.session_state:
    st.session_state.notifications = []

def show_notification(message: str, notification_type: str = "success"):
    """Add a notification to session state that will persist across reruns."""
    st.session_state.notifications.append({
        "message": message,
        "type": notification_type
    })

def clear_notifications():
    """Clear all notifications."""
    st.session_state.notifications = []

# Display persistent notifications at the top if any exist
if st.session_state.notifications:
    # Create a container for notifications
    for notification in st.session_state.notifications:
        if notification["type"] == "success":
            st.success(f"✅ {notification['message']}")
        elif notification["type"] == "error":
            st.error(f"❌ {notification['message']}")
        elif notification["type"] == "warning":
            st.warning(f"⚠️ {notification['message']}")
        elif notification["type"] == "info":
            st.info(f"ℹ️ {notification['message']}")
    
    # Button to clear notifications
    if st.button("✖️ Clear Notifications", key="clear_notifications_btn"):
        clear_notifications()
        st.rerun()
    
    st.divider()

# File upload section
    st.subheader("1️⃣ Upload Entry Forms")

# Toggle for single vs bulk upload - Make it very prominent
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("**📤 Upload Mode:**")
with col2:
    pass

upload_mode = st.radio(
    "Select upload mode:",
    options=["Single Entry", "Multiple Entries"],
    horizontal=True,
    help="Choose to process one entry form or multiple entry forms at once.",
    index=0
)

if upload_mode == "Multiple Entries":
    st.info("📁 **Multiple Entries Mode** - You can select and process several entry forms at once")

if upload_mode == "Single Entry":
    uploaded_file = st.file_uploader(
        "Choose an essay entry form",
        type=["png", "jpg", "jpeg", "pdf"],
        help="Upload a single IFI essay contest entry form"
    )
    uploaded_files = [uploaded_file] if uploaded_file else []
else:
    uploaded_files = st.file_uploader(
        "Choose multiple entry forms",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
        help="Upload multiple IFI essay contest entry forms"
    )
    if not uploaded_files:
        uploaded_files = []

# Always use Google Vision for processing
ocr_provider = "google"

# Process button
if len(uploaded_files) > 0:
    # Show file count
    if upload_mode == "Multiple Entries":
        st.info(f"📁 **{len(uploaded_files)} entry form(s) ready to process**")
    
    col1, col2 = st.columns([1, 4])
    
    with col1:
        process_btn = st.button("🚀 Process Entries", type="primary", use_container_width=True)
    
    if process_btn:
        # Initialize session state for bulk processing
        if upload_mode == "Multiple Entries":
            st.session_state.bulk_results = []
        
        try:
            # Process each file
            for idx, uploaded_file in enumerate(uploaded_files):
                if upload_mode == "Multiple Entries":
                    st.write(f"### Processing Entry {idx + 1} of {len(uploaded_files)}: `{uploaded_file.name}`")
                    progress_bar = st.progress((idx) / len(uploaded_files))
                else:
                    st.write("### Processing entry form...")
                
                try:
                    with st.spinner(f"Reading information from {uploaded_file.name}..."):
                        # Ingest the upload
                        file_bytes = uploaded_file.read()
                        ingest_data = ingest_upload(
                            uploaded_bytes=file_bytes,
                            original_filename=uploaded_file.name,
                            base_artifacts_dir="artifacts"
                        )
                        
                        # Run the pipeline
                        record, report = process_submission(
                            image_path=ingest_data["original_path"],
                            submission_id=ingest_data["submission_id"],
                            artifact_dir=ingest_data["artifact_dir"],
                            ocr_provider_name=ocr_provider,
                            original_filename=uploaded_file.name
                        )
                        
                        # Save to database
                        save_record(record, filename=uploaded_file.name)
                        
                        # Store results
                        if upload_mode == "Multiple Entries":
                            st.session_state.bulk_results.append({
                                "filename": uploaded_file.name,
                                "submission_id": ingest_data["submission_id"],
                                "record": record,
                                "report": report,
                                "artifact_dir": ingest_data["artifact_dir"],
                                "status": "✅ Success"
                            })
                            st.success(f"✅ {uploaded_file.name} - Information extracted successfully!")
                        else:
                            # Single file mode - store in original session state
                            st.session_state.processed_record = record
                            st.session_state.processing_report = report
                            st.session_state.csv_written = False
                            st.success("✅ Entry form processed successfully!")
                
                except Exception as file_error:
                    error_msg = str(file_error)
                    if upload_mode == "Multiple Entries":
                        st.session_state.bulk_results.append({
                            "filename": uploaded_file.name,
                            "submission_id": None,
                            "record": None,
                            "report": None,
                            "artifact_dir": None,
                            "status": f"❌ Error: {error_msg}"
                        })
                        st.error(f"❌ Unable to process {uploaded_file.name}: {error_msg}")
                    else:
                        raise  # Re-raise for single file mode
                
                # Update progress
                if upload_mode == "Multiple Entries":
                    progress_bar.progress((idx + 1) / len(uploaded_files))
            
            # Bulk processing summary
            if upload_mode == "Multiple Entries":
                st.write("---")
                st.write("## 📊 Processing Summary")
                
                success_count = sum(1 for r in st.session_state.bulk_results if "Success" in r["status"])
                error_count = len(st.session_state.bulk_results) - success_count
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Processed", len(st.session_state.bulk_results))
                with col2:
                    st.metric("✅ Successful", success_count)
                with col3:
                    st.metric("❌ Failed", error_count)
                
                # Show detailed results table
                st.write("### Detailed Results:")
                for result in st.session_state.bulk_results:
                    with st.expander(f"{result['status']} - {result['filename']}"):
                        if result['record']:
                            try:
                                st.json({
                                    "submission_id": result['submission_id'],
                                    "artifact_dir": result['artifact_dir'],
                                    "student_name": result['record'].student_name,
                                    "school_name": result['record'].school_name,
                                    "grade": result['record'].grade,
                                    "word_count": result['record'].word_count,
                                    "is_valid": not result['record'].needs_review,
                                    "needs_review": result['record'].needs_review
                                })
                            except AttributeError as e:
                                st.warning(f"⚠️ Error displaying record details: {e}")
                                st.json({
                                    "submission_id": result['submission_id'],
                                    "artifact_dir": result.get('artifact_dir', 'N/A'),
                                    "status": "Record available but display error occurred"
                                })
                        else:
                            st.write(result['status'])
            
        except RuntimeError as e:
            # Catch processing errors
            error_msg = str(e)
            st.error("❌ Processing Failed")
            st.error(f"Unable to process entry form: {error_msg}")
            
            # Google Cloud Vision specific help
            if "GOOGLE_APPLICATION_CREDENTIALS" in error_msg or "Vision" in error_msg or "credentials" in error_msg.lower():
                st.info("""
                **Setup Help Needed**
                
                Google Vision setup is required to read entry forms. Please contact your administrator for assistance with:
                - Google Cloud credentials
                - Cloud Vision API access
                
                Once configured, you'll be able to process entry forms.
                """)
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            st.exception(e)

# Display bulk results
if hasattr(st.session_state, 'bulk_results') and len(st.session_state.bulk_results) > 0:
    st.divider()
    st.subheader("2️⃣ Export to CSV")
    
    col1, col2 = st.columns([1, 4])
    
    with col1:
        bulk_export_btn = st.button(
            "💾 Export All to CSV",
            type="secondary",
            use_container_width=True
        )
    
    if bulk_export_btn:
        exported_count = 0
        for result in st.session_state.bulk_results:
            if result['record']:
                # Records are already saved to database during processing
                # Optionally also export to CSV
                append_to_csv(result['record'], output_dir="outputs")
                exported_count += 1
        
        st.success(f"✅ {exported_count} record(s) exported to CSV! (Records are also saved in database)")
    
    # Show database statistics
    db_stats = get_db_stats()
    
    st.markdown("**📁 Database Status:**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Records", db_stats["total_count"])
    with col2:
        st.metric("Clean Records", db_stats["clean_count"])
    with col3:
        st.metric("Needs Review", db_stats["needs_review_count"])

# Display single file results
elif st.session_state.processed_record is not None:
    st.divider()
    st.subheader("2️⃣ Entry Information")
    
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
            formatted_reasons = format_review_reasons(record.review_reason_codes)
            st.warning(f"⚠️ Needs Review: {formatted_reasons}")
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
    
    # Debug: Raw OCR + Artifacts Inspector
    with st.expander("🔎 Debug: Raw OCR Payload & Artifacts", expanded=False):
        artifact_path = Path(record.artifact_dir)
        
        # OCR JSON
        ocr_path = artifact_path / "ocr.json"
        if ocr_path.exists():
            st.subheader("📄 ocr.json")
            st.caption("Full OCR output with confidence and line-by-line text")
            ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
            st.json(ocr_data)
        
        # Raw Text
        raw_path = artifact_path / "raw_text.txt"
        if raw_path.exists():
            st.subheader("📝 raw_text.txt")
            st.caption("Complete OCR text output (what EasyOCR/Google Vision returned)")
            st.code(raw_path.read_text(encoding="utf-8"), language="text")
        
        # Contact Block (after segmentation)
        contact_path = artifact_path / "contact_block.txt"
        if contact_path.exists():
            st.subheader("👤 contact_block.txt")
            st.caption("Text fed to extraction (after segmentation)")
            st.code(contact_path.read_text(encoding="utf-8"), language="text")
        
        # Essay Block (after segmentation)
        essay_path = artifact_path / "essay_block.txt"
        if essay_path.exists():
            st.subheader("✍️ essay_block.txt")
            st.caption("Essay text (after segmentation)")
            st.code(essay_path.read_text(encoding="utf-8"), language="text")
        
        # Extraction Debug Report
        debug_path = artifact_path / "extraction_debug.json"
        if debug_path.exists():
            st.subheader("🧠 extraction_debug.json")
            st.caption("Shows which labels matched, what candidates were considered, and why each field was extracted")
            debug_data = json.loads(debug_path.read_text(encoding="utf-8"))
            st.json(debug_data)
    
    # CSV export section
    st.divider()
    st.subheader("3️⃣ Export to CSV")
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        write_csv_btn = st.button(
            "💾 Write to CSV",
            type="secondary",
            use_container_width=True,
            disabled=st.session_state.csv_written
        )
    
    if write_csv_btn:
        # Record is already saved to database during processing
        csv_path = append_to_csv(record, output_dir="outputs")
        st.session_state.csv_written = True
        
        # Show which file was written
        filename = Path(csv_path).name
        st.success(f"✅ Record written to: `{filename}` (Also saved in database)")
    
    # Manual review/approval actions
    # Records are automatically saved to database, so actions work immediately
    if True:  # Always show actions since records are in database
        st.markdown("**🔄 Manual Actions:**")
        col1, col2 = st.columns(2)
        
        with col1:
            if record.needs_review:
                if st.button("✅ Approve & Move to Clean", type="primary", use_container_width=True):
                    if update_db_record(record.submission_id, {"needs_review": False}):
                        st.success("✅ Record approved and moved to clean batch!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to move record")
            else:
                if st.button("⚠️ Send for Review", type="secondary", use_container_width=True):
                    if update_db_record(record.submission_id, {"needs_review": True}):
                        st.success("⚠️ Record sent for review!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to move record")
        
        with col2:
            st.caption("💡 Use these buttons to manually move records between review and approved batches.")
    
    # Show database statistics
    db_stats = get_db_stats()
    
    st.markdown("**📁 Database Status:**")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Records", db_stats["total_count"])
    with col2:
        st.metric("Clean Records", db_stats["clean_count"])
    with col3:
        st.metric("Needs Review", db_stats["needs_review_count"])

# Review and Approval Workflow
st.divider()
st.subheader("4️⃣ Review & Approval Workflow")

# Show database stats at top
db_stats = get_db_stats()
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("📊 Total Records", db_stats["total_count"])
with col2:
    st.metric("✅ Clean Records", db_stats["clean_count"])
with col3:
    st.metric("⚠️ Needs Review", db_stats["needs_review_count"])

# Initialize session state for review interface
if "review_mode" not in st.session_state:
    st.session_state.review_mode = "Needs Review"
if "editing_record_id" not in st.session_state:
    st.session_state.editing_record_id = None

# Mode selector
review_mode = st.radio(
    "Review Mode",
    options=["Needs Review", "Approved Records"],
    horizontal=True,
    index=0 if st.session_state.review_mode == "Needs Review" else 1,
    key="review_mode_radio"
)
st.session_state.review_mode = review_mode

# Load appropriate records from database
if review_mode == "Needs Review":
    records = get_db_records(needs_review=True)
    action_label = "Approve"
else:
    records = get_db_records(needs_review=False)
    action_label = "Send for Review"

# Show count
if records:
    st.info(f"📋 Found **{len(records)}** record(s) in {review_mode.lower()}")
else:
    st.info(f"📋 No records found in {review_mode.lower()}")

# Display records
if records:
    for idx, record_dict in enumerate(records):
        submission_id = record_dict.get("submission_id", "")
        
        with st.expander(
            f"{'⚠️' if review_mode == 'Needs Review' else '✅'} {submission_id} - {record_dict.get('student_name', 'Unknown')}",
            expanded=(st.session_state.editing_record_id == submission_id)
        ):
            # Check if this record is being edited
            is_editing = (st.session_state.editing_record_id == submission_id)
            
            if is_editing:
                # Edit mode
                col1, col2 = st.columns(2)
                
                with col1:
                    edited_student_name = st.text_input(
                        "Student Name",
                        value=record_dict.get("student_name", ""),
                        key=f"edit_student_{submission_id}"
                    )
                    edited_school_name = st.text_input(
                        "School Name",
                        value=record_dict.get("school_name", ""),
                        key=f"edit_school_{submission_id}"
                    )
                    edited_grade = st.text_input(
                        "Grade",
                        value=record_dict.get("grade", ""),
                        key=f"edit_grade_{submission_id}",
                        help="Enter grade as number (e.g., 5) or grade level (e.g., 5th Grade)"
                    )
                    edited_teacher_name = st.text_input(
                        "Teacher Name",
                        value=record_dict.get("teacher_name", ""),
                        key=f"edit_teacher_{submission_id}"
                    )
                    edited_city = st.text_input(
                        "City/Location",
                        value=record_dict.get("city_or_location", ""),
                        key=f"edit_city_{submission_id}"
                    )
                
                with col2:
                    edited_father_figure = st.text_input(
                        "Father Figure Name",
                        value=record_dict.get("father_figure_name", ""),
                        key=f"edit_father_{submission_id}"
                    )
                    edited_phone = st.text_input(
                        "Phone",
                        value=record_dict.get("phone", ""),
                        key=f"edit_phone_{submission_id}"
                    )
                    edited_email = st.text_input(
                        "Email",
                        value=record_dict.get("email", ""),
                        key=f"edit_email_{submission_id}"
                    )
                    st.text(f"Word Count: {record_dict.get('word_count', 0)}")
                    ocr_conf = record_dict.get('ocr_confidence_avg')
                    if ocr_conf:
                        st.text(f"OCR Confidence: {float(ocr_conf):.2%}")
                    else:
                        st.text("OCR Confidence: N/A")
                    
                    # Format review reasons nicely
                    review_reasons = record_dict.get("review_reason_codes", "")
                    if review_reasons:
                        formatted_reasons = format_review_reasons(review_reasons)
                        st.markdown(f"**⚠️ Review Reasons:** {formatted_reasons}")
                    
                    # Add PDF download and path info
                    pdf_path = get_pdf_path(record_dict.get("artifact_dir", ""))
                    if pdf_path and pdf_path.exists():
                        try:
                            with open(pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                            
                            st.markdown("**📄 Original PDF File:**")
                            
                            # Download button
                            st.download_button(
                                label="⬇️ Download PDF to View",
                                data=pdf_bytes,
                                file_name=pdf_path.name,
                                mime="application/pdf",
                                key=f"pdf_dl_{submission_id}_edit",
                                use_container_width=True
                            )
                            
                            # Show file path
                            st.caption(f"📍 File path: `{pdf_path}`")
                            st.info("💡 **Tip:** Click the download button above, then open the downloaded PDF with your browser or PDF viewer.")
                        except Exception as e:
                            st.caption(f"PDF file: {pdf_path.name} (Error: {str(e)})")
                    elif pdf_path:
                        st.caption(f"PDF file: {pdf_path.name}")
                
                # Action buttons
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1:
                    if st.button("💾 Save Changes", key=f"save_{submission_id}", type="primary"):
                        # Parse grade - handle None values
                        grade = None
                        if edited_grade:
                            grade_str = edited_grade.strip()
                            if grade_str:
                                try:
                                    # Try to extract number from "5th Grade" or just "5"
                                    import re
                                    grade_match = re.search(r'\d+', grade_str)
                                    if grade_match:
                                        grade = int(grade_match.group())
                                except:
                                    pass
                        
                        # Create updated record - handle None values before calling strip()
                        updated_record = SubmissionRecord(
                            submission_id=submission_id,
                            student_name=edited_student_name.strip() if edited_student_name else None,
                            school_name=edited_school_name.strip() if edited_school_name else None,
                            grade=grade,
                            teacher_name=edited_teacher_name.strip() if edited_teacher_name else None,
                            city_or_location=edited_city.strip() if edited_city else None,
                            father_figure_name=edited_father_figure.strip() if edited_father_figure else None,
                            phone=edited_phone.strip() if edited_phone else None,
                            email=edited_email.strip() if edited_email else None,
                            word_count=int(record_dict.get("word_count", 0)),
                            ocr_confidence_avg=float(record_dict.get("ocr_confidence_avg")) if record_dict.get("ocr_confidence_avg") else None,
                            needs_review=record_dict.get("needs_review", False),
                            review_reason_codes=record_dict.get("review_reason_codes", ""),
                            artifact_dir=record_dict.get("artifact_dir", "")
                        )
                        
                        # Update in database
                        updates = {
                            "student_name": updated_record.student_name,
                            "school_name": updated_record.school_name,
                            "grade": updated_record.grade,
                            "teacher_name": updated_record.teacher_name,
                            "city_or_location": updated_record.city_or_location,
                            "father_figure_name": updated_record.father_figure_name,
                            "phone": updated_record.phone,
                            "email": updated_record.email,
                            "needs_review": updated_record.needs_review,
                            "review_reason_codes": updated_record.review_reason_codes
                        }
                        if update_db_record(submission_id, updates):
                            show_notification("Record updated successfully!", "success")
                            st.session_state.editing_record_id = None
                            st.rerun()
                        else:
                            show_notification("Failed to update record", "error")
                            st.rerun()
                
                with col2:
                    # Delete button with confirmation in edit mode
                    delete_key = f"delete_confirm_{submission_id}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False
                    
                    if st.session_state[delete_key]:
                        # Show confirmation warning
                        st.warning(f"⚠️ **Are you sure you want to delete this record?**\n\nThis will permanently delete the record for: **{record_dict.get('student_name', 'Unknown')}** (ID: {submission_id})")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ Yes, Delete", key=f"delete_yes_{submission_id}", type="primary"):
                                if delete_db_record(submission_id):
                                    show_notification("Record deleted successfully!", "success")
                                    st.session_state.editing_record_id = None
                                    # Clear confirmation state
                                    st.session_state[delete_key] = False
                                    st.rerun()
                                else:
                                    show_notification("Failed to delete record", "error")
                                    st.session_state[delete_key] = False
                                    st.rerun()
                        with col_no:
                            if st.button("❌ Cancel", key=f"delete_no_{submission_id}"):
                                st.session_state[delete_key] = False
                                st.rerun()
                    else:
                        if st.button("🗑️ Delete", key=f"delete_{submission_id}", type="secondary"):
                            st.session_state[delete_key] = True
                            st.rerun()
                
                col_cancel, col_action = st.columns([1, 1])
                with col_cancel:
                    if st.button("❌ Cancel Edit", key=f"cancel_{submission_id}"):
                        st.session_state.editing_record_id = None
                        st.rerun()
                
                with col_action:
                    if review_mode == "Needs Review":
                        if st.button(f"✅ {action_label}", key=f"approve_{submission_id}", type="secondary"):
                            if update_db_record(submission_id, {"needs_review": False}):
                                show_notification("Record approved and moved to clean batch!", "success")
                                st.session_state.editing_record_id = None
                                st.rerun()
                            else:
                                show_notification("Failed to approve record", "error")
                                st.rerun()
                    else:
                        if st.button(f"⚠️ {action_label}", key=f"review_{submission_id}", type="secondary"):
                            if update_db_record(submission_id, {"needs_review": True}):
                                show_notification("Record sent for review!", "warning")
                                st.session_state.editing_record_id = None
                                st.rerun()
                            else:
                                show_notification("Failed to send record for review", "error")
                                st.rerun()
            else:
                # View mode
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Contact Information:**")
                    st.text(f"Student: {record_dict.get('student_name', 'N/A')}")
                    st.text(f"School: {record_dict.get('school_name', 'N/A')}")
                    st.text(f"Grade: {record_dict.get('grade', 'N/A')}")
                    if record_dict.get('teacher_name'):
                        st.text(f"Teacher: {record_dict.get('teacher_name')}")
                    if record_dict.get('city_or_location'):
                        st.text(f"Location: {record_dict.get('city_or_location')}")
                
                with col2:
                    st.markdown("**Additional Info:**")
                    if record_dict.get('father_figure_name'):
                        st.text(f"Father Figure: {record_dict.get('father_figure_name')}")
                    if record_dict.get('phone'):
                        st.text(f"Phone: {record_dict.get('phone')}")
                    if record_dict.get('email'):
                        st.text(f"Email: {record_dict.get('email')}")
                    st.text(f"Word Count: {record_dict.get('word_count', 0)}")
                    ocr_conf = record_dict.get('ocr_confidence_avg')
                    if ocr_conf:
                        st.text(f"OCR Confidence: {float(ocr_conf):.2%}")
                    else:
                        st.text("OCR Confidence: N/A")
                    
                    # Format review reasons nicely
                    review_reasons = record_dict.get("review_reason_codes", "")
                    if review_reasons:
                        formatted_reasons = format_review_reasons(review_reasons)
                        st.markdown(f"**⚠️ Review Reasons:** {formatted_reasons}")
                    
                    # Add PDF download and path info
                    pdf_path = get_pdf_path(record_dict.get("artifact_dir", ""))
                    if pdf_path and pdf_path.exists():
                        try:
                            with open(pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                            
                            st.markdown("**📄 Original PDF File:**")
                            
                            # Download button
                            st.download_button(
                                label="⬇️ Download PDF to View",
                                data=pdf_bytes,
                                file_name=pdf_path.name,
                                mime="application/pdf",
                                key=f"pdf_dl_{submission_id}_view",
                                use_container_width=True
                            )
                            
                            # Show file path
                            st.caption(f"📍 File path: `{pdf_path}`")
                            st.info("💡 **Tip:** Click the download button above, then open the downloaded PDF with your browser or PDF viewer.")
                        except Exception as e:
                            st.caption(f"PDF file: {pdf_path.name} (Error: {str(e)})")
                    elif pdf_path:
                        st.caption(f"PDF file: {pdf_path.name}")
                
                # Action buttons
                col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                with col1:
                    if st.button("✏️ Edit", key=f"edit_btn_{submission_id}"):
                        st.session_state.editing_record_id = submission_id
                        st.rerun()
                
                with col2:
                    # Quick action button
                    if review_mode == "Needs Review":
                        if st.button(f"✅ {action_label}", key=f"quick_approve_{submission_id}", type="primary"):
                            if update_db_record(submission_id, {"needs_review": False}):
                                show_notification("Record approved!", "success")
                                st.rerun()
                            else:
                                show_notification("Failed to approve record", "error")
                                st.rerun()
                    else:
                        if st.button(f"⚠️ {action_label}", key=f"quick_review_{submission_id}", type="secondary"):
                            if update_db_record(submission_id, {"needs_review": True}):
                                show_notification("Record sent for review!", "warning")
                                st.rerun()
                            else:
                                show_notification("Failed to send record for review", "error")
                                st.rerun()
                
                with col3:
                    # Delete button with confirmation in view mode
                    delete_key = f"delete_confirm_view_{submission_id}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False
                    
                    if st.session_state[delete_key]:
                        # Show confirmation warning
                        st.warning(f"⚠️ **Confirm deletion?**\n\nDelete **{record_dict.get('student_name', 'Unknown')}** (ID: {submission_id})?")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ Delete", key=f"delete_yes_view_{submission_id}", type="primary"):
                                if delete_db_record(submission_id):
                                    show_notification("Record deleted successfully!", "success")
                                    # Clear confirmation state
                                    st.session_state[delete_key] = False
                                    st.rerun()
                                else:
                                    show_notification("Failed to delete record", "error")
                                    st.session_state[delete_key] = False
                                    st.rerun()
                        with col_no:
                            if st.button("❌ Cancel", key=f"delete_no_view_{submission_id}"):
                                st.session_state[delete_key] = False
                                st.rerun()
                    else:
                        if st.button("🗑️ Delete", key=f"delete_view_{submission_id}", type="secondary"):
                            st.session_state[delete_key] = True
                            st.rerun()
                
                # Show artifact info
                if record_dict.get("artifact_dir"):
                    with st.expander("📁 Artifact Details"):
                        st.text(f"Artifact Directory: {record_dict.get('artifact_dir')}")

# Footer
st.divider()
st.caption("💡 IFI Essay Gateway is an internal intake and review assistant that helps manage thousands of student essays submitted each year for the Illinois Fatherhood Initiative's fatherhood essay contest. By organizing entries and reducing paperwork for our volunteer team, it supports IFI's mission to engage fathers in the lives of their children and to honor real, child‑voiced stories of dads and father‑figures across Illinois.")

