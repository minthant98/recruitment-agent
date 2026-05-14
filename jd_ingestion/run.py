"""
run.py — CLI entry point for JD ingestion.

Usage:
    python -m jd_ingestion.run

This will process all 3 JD files and load them into Supabase.
Run this once before starting the pipeline.
"""
from pathlib import Path
from jd_ingestion.parser import extract_text_from_docx
from jd_ingestion.extractor import extract_jd_structure
from jd_ingestion.loader import load_jd_to_supabase

# ── JD configuration ──────────────────────────────────────────────
# Add your department head details here before running
JDS = [
    {
        "file": "jds/Senior Data Analyst  (JD).docx",
        "dept_name": "Finance",
        "dept_head_name": "Min Thant",        # fill in before running
        "dept_head_email": "minthanttin19@gmail.com",       # fill in before running
    },
    {
        "file": "jds/Network Engineer (Supervisor).docx",
        "dept_name": "TODC",
        "dept_head_name": "David",        # fill in before running
        "dept_head_email": "minthanttin98@gmailcom",       # fill in before running
    },
    {
        "file": "jds/Junior Network Engineer - JD.docx",
        "dept_name": "TODC",
        "dept_head_name": "David",        # fill in same as above
        "dept_head_email": "minthanttin98@gmailcom",       # fill in same as above
    },
]
# ─────────────────────────────────────────────────────────────────


def run():
    print("Starting JD ingestion...\n")
    results = []

    for jd_config in JDS:
        file_path = jd_config["file"]
        print(f"Processing: {file_path}")

        # Validate dept head info is filled in
        if not jd_config["dept_head_name"] or not jd_config["dept_head_email"]:
            print(f"  ❌ SKIPPED — fill in dept_head_name and dept_head_email in run.py first\n")
            continue

        try:
            # Step 1: Extract text from Word file
            raw_text = extract_text_from_docx(file_path)
            print(f"  Extracted {len(raw_text)} characters from Word file")

            # Step 2: Call Groq to structure the JD
            extracted = extract_jd_structure(raw_text)
            print(f"  Groq extracted: {extracted['role_title']}")

            # Step 3: Load into Supabase
            result = load_jd_to_supabase(
                dept_name=jd_config["dept_name"],
                dept_head_name=jd_config["dept_head_name"],
                dept_head_email=jd_config["dept_head_email"],
                source_file=Path(file_path).name,
                raw_text=raw_text,
                extracted=extracted,
            )
            results.append(result)
            print(f"  ✅ Done\n")

        except FileNotFoundError as e:
            print(f"  ❌ File not found: {e}\n")
        except Exception as e:
            print(f"  ❌ Failed: {e}\n")

    print("─" * 50)
    print(f"Ingestion complete. {len(results)}/{len(JDS)} JDs loaded.")
    for r in results:
        print(f"  {r['role_title']} → jd_id: {r['jd_id']}")


if __name__ == "__main__":
    run()