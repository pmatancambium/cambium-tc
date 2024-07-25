import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import holidays
import calendar

# Set page config
st.set_page_config(page_title="TimeCamp Employee Status", layout="wide")

# Custom CSS (unchanged)
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
    .holiday-list {
        background-color: #e1e4e8;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 20px;
    }
    .holiday-item {
        margin: 5px 0;
    }
    .stButton > button {
        width: 100%;
        height: 30px;
        padding: 0px;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600)
def get_israeli_holidays(year):
    il_holidays = holidays.IL(years=year)
    return {date.strftime("%Y-%m-%d"): name for date, name in il_holidays.items()}


def fetch_data(api_key, year, month):
    first_day = datetime(year, month, 1)

    # Adjust the last day to today if it's the current month and year
    if year == datetime.now().year and month == datetime.now().month:
        last_day = datetime.now()
    else:
        last_day = (
            first_day.replace(day=1, month=month % 12 + 1) - timedelta(days=1)
            if month < 12
            else datetime(year + 1, 1, 1) - timedelta(days=1)
        )

    date_range = [
        first_day + timedelta(days=i) for i in range((last_day - first_day).days + 1)
    ]

    # Get Israeli holidays for the selected year
    il_holidays = get_israeli_holidays(year)

    results = []

    for date in date_range:
        if (
            date.weekday() in {6, 0, 1, 2, 3}
            and date.strftime("%Y-%m-%d") not in il_holidays
        ):  # Sunday to Thursday, excluding holidays
            work_hours = get_work_hours(api_key, date)
            results.append((date, work_hours))

    return results, il_holidays


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


def display_holidays(il_holidays, year, month):
    selected_month_holidays = {
        date: name
        for date, name in il_holidays.items()
        if datetime.strptime(date, "%Y-%m-%d").month == month
        and datetime.strptime(date, "%Y-%m-%d").year == year
    }

    if selected_month_holidays:
        st.subheader(f"Holidays in {calendar.month_name[month]} {year}")
        st.markdown('<div class="holiday-list">', unsafe_allow_html=True)
        for date, holiday_name in selected_month_holidays.items():
            formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d %B")
            st.markdown(
                f'<div class="holiday-item">🗓 {formatted_date}: {holiday_name}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info(f"There are no holidays in {calendar.month_name[month]} {year}.")


def main():
    st.title("TimeCamp Employee Status")

    # Sidebar
    st.sidebar.header("Settings")
    api_key = st.sidebar.text_input("API Key:", type="password")

    # Year and Month selection
    current_year = datetime.now().year
    current_month = datetime.now().month
    year = st.sidebar.selectbox(
        "Select Year", range(current_year - 2, current_year + 3), index=2
    )
    month = st.sidebar.selectbox(
        "Select Month",
        range(1, 13),
        index=current_month - 1,
        format_func=lambda x: calendar.month_name[x],
    )

    if st.sidebar.button("Fetch Data"):
        if not api_key:
            st.sidebar.error("Please enter an API key.")
        else:
            with st.spinner("Fetching data..."):
                data, il_holidays = fetch_data(api_key, year, month)

            # Display holidays for the selected month
            display_holidays(il_holidays, year, month)

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
                st.subheader(
                    f"Daily Work Hours for {calendar.month_name[month]} {year}"
                )
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

                # Create a new DataFrame with the styled data and an additional column for the button
                display_df = styled_df.data.copy()
                display_df["TimeCamp Link"] = display_df["Date"].apply(
                    lambda x: f'<a href="https://app.timecamp.com/app#/timesheets/timer/{x.strftime("%Y-%m-%d")}" target="_blank"><button>View in TimeCamp</button></a>'
                )

                # Display the DataFrame with the new button column
                st.write(
                    display_df.to_html(escape=False, index=False),
                    unsafe_allow_html=True,
                )

            else:
                st.error(
                    "Failed to fetch data. Please check your API key and try again."
                )


if __name__ == "__main__":
    main()
