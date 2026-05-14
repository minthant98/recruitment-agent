"""
loader.py — Insert extracted JD data into Supabase.
"""
from db.queries import (
    get_department_by_name,
    insert_department,
    insert_job_description,
    insert_screening_criteria,
)


def load_jd_to_supabase(
    dept_name: str,
    dept_head_name: str,
    dept_head_email: str,
    source_file: str,
    raw_text: str,
    extracted: dict,
) -> dict:
    """
    Upsert department, insert JD and screening criteria.
    Returns a summary dict with all inserted IDs.
    """

    # 1. Get or create department
    dept = get_department_by_name(dept_name)
    if not dept:
        dept = insert_department(
            name=dept_name,
            head_name=dept_head_name,
            head_email=dept_head_email,
        )
        print(f"  Created department: {dept_name}")
    else:
        print(f"  Department exists: {dept_name}")

    # 2. Insert job description
    jd = insert_job_description(
        dept_id=dept["id"],
        role_title=extracted["role_title"],
        seniority_level=extracted.get("seniority_level"),
        required_years=extracted.get("required_years"),
        raw_text=raw_text,
        source_file=source_file,
    )
    print(f"  Inserted JD: {extracted['role_title']} (id: {jd['id']})")

    # 3. Insert screening criteria
    criteria = insert_screening_criteria(
        jd_id=jd["id"],
        criteria=extracted["screening_criteria"],
    )
    print(f"  Inserted {len(criteria)} screening criteria")

    return {
        "dept_id": dept["id"],
        "jd_id": jd["id"],
        "role_title": extracted["role_title"],
        "criteria_count": len(criteria),
    }