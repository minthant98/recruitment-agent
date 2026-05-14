from supabase import create_client, Client
from config import get_settings


def get_db() -> Client:
    """
    Return a fresh Supabase client per call.
    Thread-safe — each background thread gets its own connection.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_key)