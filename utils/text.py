"""
text.py — Text cleaning and matching helpers used across nodes.
"""
import re


def clean_text(text: str) -> str:
    """Remove excessive whitespace and normalize line breaks."""
    text = re.sub(r'\r\n|\r', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def fuzzy_match_jd(
    email_subject: str,
    email_body: str,
    jd_list: list[dict],
) -> dict | None:
    """
    Match an email to the most relevant JD using keyword scoring.

    LEGACY interface — returns best JD dict or None.
    Kept for any code that still calls this directly.
    Internally calls fuzzy_match_jd_scored and unwraps the result.
    """
    result = fuzzy_match_jd_scored(email_subject, email_body, jd_list)
    if result["tier"] == "LOW":
        return None
    return result["top_matches"][0]["jd"] if result["top_matches"] else None


def fuzzy_match_jd_scored(
    email_subject: str,
    email_body: str,
    jd_list: list[dict],
) -> dict:
    """
    Match an email to JDs and return a confidence score + tier + top matches.

    Confidence tiers:
        HIGH   >= 0.80  → auto-assign, screening runs immediately
        MEDIUM  0.50–0.79 → pause, recruiter confirms job match
        LOW    < 0.50   → unmatched queue, recruiter assigns manually

    Returns:
        {
            "confidence": float,          # 0.0 – 1.0
            "tier": "HIGH"|"MEDIUM"|"LOW",
            "top_matches": [              # sorted best → worst
                {
                    "jd": dict,           # full JD row from Supabase
                    "score": float,       # raw keyword score
                    "confidence": float,  # normalised 0.0–1.0
                },
                ...
            ]
        }
    """
    if not jd_list:
        return {"confidence": 0.0, "tier": "LOW", "top_matches": []}

    search_text = f"{email_subject} {email_body}".lower()
    raw_scores = []

    for jd in jd_list:
        score = 0
        role_title = jd.get("role_title", "").lower()
        words = role_title.split()
        significant_words = [w for w in words if len(w) > 3]

        # Score each significant word in the role title
        for word in significant_words:
            if word in search_text:
                score += 1

        # Bonus: full title appears verbatim
        if role_title in search_text:
            score += 3

        # Bonus: title words appear in subject specifically (stronger signal)
        subject_lower = email_subject.lower()
        for word in significant_words:
            if word in subject_lower:
                score += 1

        raw_scores.append((score, jd))

    # Sort best → worst
    raw_scores.sort(key=lambda x: x[0], reverse=True)

    best_score = raw_scores[0][0]
    second_score = raw_scores[1][0] if len(raw_scores) > 1 else 0

    # ── Normalise to 0.0–1.0 confidence ─────────────────────────
    # Max possible score: all significant words matched (1 each)
    # + full title bonus (3) + subject bonus (1 per word)
    # We estimate max as: n_significant_words * 2 + 3
    best_jd_words = [
        w for w in raw_scores[0][1].get("role_title", "").lower().split()
        if len(w) > 3
    ]
    max_possible = max(len(best_jd_words) * 2 + 3, 1)
    raw_confidence = min(best_score / max_possible, 1.0)

    # ── Separation penalty ───────────────────────────────────────
    # If two JDs score similarly, we're less confident in the top pick.
    # Reduce confidence proportionally to how close the second score is.
    if best_score > 0 and second_score > 0:
        separation = (best_score - second_score) / best_score
        # separation = 1.0 means clear winner, 0.0 means tied
        # Apply mild penalty when scores are close (separation < 0.3)
        if separation < 0.3:
            raw_confidence *= (0.7 + separation)

    confidence = round(min(max(raw_confidence, 0.0), 1.0), 4)

    # ── Tier assignment ──────────────────────────────────────────
    if best_score == 0:
        tier = "LOW"
        confidence = 0.0
    elif confidence >= 0.80:
        tier = "HIGH"
    elif confidence >= 0.50:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    # Build top_matches list (all JDs with score > 0, max 3)
    top_matches = []
    for score, jd in raw_scores:
        if score == 0:
            break
        jd_words = [w for w in jd.get("role_title", "").lower().split() if len(w) > 3]
        max_p = max(len(jd_words) * 2 + 3, 1)
        jd_conf = round(min(score / max_p, 1.0), 4)
        top_matches.append({
            "jd": jd,
            "score": score,
            "confidence": jd_conf,
        })
        if len(top_matches) >= 3:
            break

    return {
        "confidence": confidence,
        "tier": tier,
        "top_matches": top_matches,
    }