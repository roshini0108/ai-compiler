import streamlit as st
import requests

st.set_page_config(
    page_title="AI Application Compiler",
    layout="wide"
)

st.title("🚀 AI Application Compiler")

prompt = st.text_area(
    "Enter Application Requirements",
    height=150,
    placeholder="Build a CRM with login, contacts, dashboard..."
)

if st.button("Compile Application"):

    with st.spinner("Compiling..."):

        response = requests.post(
            "http://localhost:8000/compile",
            json={"prompt": prompt}
        )

        result = response.json()

    st.success("Compilation Complete!")

    st.subheader("Intent")
    st.json(result.get("intent", {}))

    st.subheader("Intermediate Representation")
    st.json(result.get("ir", {}))

    st.subheader("Database Schema")
    st.json(result.get("db_schema", {}))

    st.subheader("API Schema")
    st.json(result.get("api_schema", {}))

    st.subheader("RBAC")
    st.json(result.get("rbac", {}))

    st.subheader("Validation")
    st.json(result.get("validation", {}))