import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px

# Set page config
st.set_page_config(page_title="TimeCamp Employee Status", layout="wide")

# Custom CSS
st.markdown(
    """
<style>
    .reportview-container {
        background-color: #f0f2f6;
    }
    .big-font {
        font-size:20px !important;
        font-weight: bold;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600)
def fetch_data(api_key):
    today = datetime.today()
    first_day = today.replace(day=1)
    date_range = [
        first_day + timedelta(days=i) for i in range((today - first_day).days + 1)
    ]

    results = []

    for date in date_range:
        if date.weekday() in {6, 0, 1, 2, 3}:  # Sunday to Thursday
            work_hours = get_work_hours(api_key, date)
            results.append((date, work_hours))

    return results


def get_work_hours(api_key, date):
    url = "https://app.timecamp.com/third_party/api/entries"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    params = {
        "from": date.strftime("%Y-%m-%d"),
        "to": date.strftime("%Y-%m-%d"),
        "user_ids": "me",
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        entries = response.json()
        total_seconds = sum(int(entry["duration"]) for entry in entries)
        return total_seconds / 3600
    else:
        return None


def main():
    st.title("TimeCamp Employee Status")

    # Sidebar
    st.sidebar.header("Settings")
    api_key = st.sidebar.text_input("API Key:", type="password")

    if st.sidebar.button("Fetch Data"):
        if not api_key:
            st.sidebar.error("Please enter an API key.")
        else:
            with st.spinner("Fetching data..."):
                data = fetch_data(api_key)

            if data:
                df = pd.DataFrame(data, columns=["Date", "Hours"])
                df["Date"] = pd.to_datetime(df["Date"])
                df["Day"] = df["Date"].dt.day_name()
                df["Min Hours"] = df["Day"].map(
                    {
                        "Thursday": 8,
                        "Friday": 8,
                        "Saturday": 8,
                        "Sunday": 8.5,
                        "Monday": 8.5,
                        "Tuesday": 8.5,
                        "Wednesday": 8.5,
                    }
                )
                df["Status"] = df.apply(
                    lambda row: (
                        "OK"
                        if pd.notnull(row["Hours"]) and row["Hours"] >= row["Min Hours"]
                        else "Warning"
                    ),
                    axis=1,
                )
                df["Missing Hours"] = df.apply(
                    lambda row: (
                        max(0, row["Min Hours"] - (row["Hours"] or 0))
                        if pd.notnull(row["Hours"])
                        else row["Min Hours"]
                    ),
                    axis=1,
                )

                # Summary statistics
                total_hours = df["Hours"].sum()
                total_missing = df["Missing Hours"].sum()
                warning_days = df[df["Status"] == "Warning"].shape[0]

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Hours Worked", f"{total_hours:.2f}")
                with col2:
                    st.metric("Total Missing Hours", f"{total_missing:.2f}")
                with col3:
                    st.metric("Days with Warnings", warning_days)

                # Visualizations
                st.subheader("Daily Work Hours")
                fig = px.bar(
                    df,
                    x="Date",
                    y="Hours",
                    color="Status",
                    hover_data=["Day", "Min Hours", "Missing Hours"],
                    labels={"Hours": "Work Hours"},
                    color_discrete_map={"OK": "green", "Warning": "red"},
                )
                fig.add_scatter(
                    x=df["Date"],
                    y=df["Min Hours"],
                    mode="lines",
                    name="Minimum Hours",
                    line=dict(color="blue", dash="dash"),
                )
                st.plotly_chart(fig, use_container_width=True)

                # Detailed table
                st.subheader("Detailed Work Log")

                # Function to apply color to Status column
                def color_status(val):
                    return f'background-color: {"yellow" if val == "Warning" else ""}'

                # Apply styling
                styled_df = (
                    df[["Date", "Day", "Hours", "Min Hours", "Missing Hours", "Status"]]
                    .sort_values("Date", ascending=False)
                    .style.applymap(color_status, subset=["Status"])
                    .format(
                        {
                            "Date": lambda x: x.strftime("%Y-%m-%d"),
                            "Hours": "{:.2f}",
                            "Min Hours": "{:.2f}",
                            "Missing Hours": "{:.2f}",
                        }
                    )
                )

                st.dataframe(styled_df, use_container_width=True)
            else:
                st.error(
                    "Failed to fetch data. Please check your API key and try again."
                )


if __name__ == "__main__":
    main()
