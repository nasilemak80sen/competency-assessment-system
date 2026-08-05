"""
navigation.py - Persistent Navigation Component
"""
import streamlit as st

PAGES = {
    "🏠 Dashboard": "🏠 Dashboard Home",
    "🌡️ Heatmap": "🌡️ Competency Heatmap",
    "👤 Assessment": "👤 Individual Assessment & Talent Profile",
    "🎯 Readiness": "🎯 Readiness & Gaps",
    "📊 Charts": "📊 Chart Builder & Depth Analysis",
}

ADMIN_PAGES = {
    "📥 Import": "⚙️ Admin: Import Data",
    "👥 Personnel": "⚙️ Admin: Personnel CRUD",
    "📝 Entry": "⚙️ Admin: Assessment Entry",
}

# Add breadcrumb at top of each page

def show_breadcrumb():
    """Display breadcrumb navigation."""
    current = st.session_state.get("current_page", "🏠 Dashboard Home")
    
    breadcrumb_items = {
        "🏠 Dashboard Home": ["Home"],
        "🌡️ Competency Heatmap": ["Home", "CompetencyHeatmap"],
        "👤 Individual Assessment & Talent Profile": ["Home", "Talent Profile"],
        "🎯 Readiness & Gaps": ["Home", "Talent Readiness"],
        "📊 Chart Builder & Depth Analysis": ["Home", "Chart Builder & Analysis"],
        "⚙️ Admin: Import Data": ["Admin", "Import"],
        "⚙️ Admin: Personnel CRUD": ["Admin", "Personnel CRUD"],
        "⚙️ Admin: Assessment Entry": ["Admin", "Entry"],
    }
    
    breadcrumbs = breadcrumb_items.get(current, ["Home"])
    st.caption(" > ".join(breadcrumbs))

def init_session():
    """Initialize navigation session state."""
    if "current_page" not in st.session_state:
        st.session_state.current_page = "🏠 Dashboard Home"
    if "show_admin" not in st.session_state:
        st.session_state.show_admin = False

def render_navigation():
    """Render top navigation bar."""
    init_session()
    
    nav_container = st.container()
    
    with nav_container:
        # Title row
        col_title, col_right = st.columns([0.85, 0.15])
        
        with col_title:
            st.markdown("### 📊 RE Fraternity Competency Assessment v3.0")
        
        # Divider
        st.markdown("---")
        
        # Main pages navigation
        nav_cols = st.columns(5)
        
        for idx, (display_name, actual_name) in enumerate(PAGES.items()):
            with nav_cols[idx]:
                is_active = st.session_state.current_page == actual_name
                
                if st.button(
                    display_name,
                    use_container_width=True,
                    key=f"nav_{idx}",
                    disabled=is_active,
                ):
                    st.session_state.current_page = actual_name
                    st.rerun()
        
        # Admin section
        st.markdown("")
        
        admin_col1, admin_col2, admin_col3, admin_col_spacer = st.columns([1, 1, 1, 2])
        
        for idx, (display_name, actual_name) in enumerate(ADMIN_PAGES.items()):
            with [admin_col1, admin_col2, admin_col3][idx]:
                if st.button(
                    f"⚙️ {display_name}",
                    use_container_width=True,
                    key=f"admin_{idx}",
                ):
                    st.session_state.current_page = actual_name
                    st.rerun()
        
        st.markdown("---")
    
    return st.session_state.current_page