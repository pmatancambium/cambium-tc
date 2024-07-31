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
    .highlight-warning {
        background-color: yellow !important;
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
            work_hours, tasks = get_work_hours_and_tasks(api_key, date)
            results.append((date, work_hours, tasks))

    return results, il_holidays


def get_work_hours_and_tasks(api_key, date):
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
        tasks = [entry["name"] for entry in entries if entry["name"]]
        return total_seconds / 3600, tasks
    else:
        return None, []


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

    # Add a date range picker for custom date selection
    use_custom_date = st.sidebar.checkbox("Use custom date range")
    if use_custom_date:
        start_date = st.sidebar.date_input("Start date", datetime(year, month, 1))
        end_date = st.sidebar.date_input("End date", datetime(year, month, 28))

    if st.sidebar.button("Fetch Data"):
        if not api_key:
            st.sidebar.error("Please enter an API key.")
        else:
            with st.spinner("Fetching data..."):
                if use_custom_date:
                    data, il_holidays = fetch_data(
                        api_key, start_date.year, start_date.month
                    )
                    data = [d for d in data if start_date <= d[0].date() <= end_date]
                else:
                    data, il_holidays = fetch_data(api_key, year, month)

            # Display holidays for the selected month
            display_holidays(il_holidays, year, month)

            if data:
                df = pd.DataFrame(data, columns=["Date", "Hours", "Tasks"])
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
                        if pd.notnull(row["Hours"])
                        and row["Min Hours"] <= row["Hours"] <= 11.5
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

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Hours Worked", f"{total_hours:.2f}")
                with col2:
                    st.metric("Total Missing Hours", f"{total_missing:.2f}")
                with col3:
                    st.metric("Days with Warnings", warning_days)
                with col4:
                    avg_hours_per_day = total_hours / len(df)
                    st.metric("Average Hours per Day", f"{avg_hours_per_day:.2f}")

                # Visualizations
                st.subheader(
                    f"Daily Work Hours for {calendar.month_name[month]} {year}"
                )
                fig = px.bar(
                    df,
                    x="Date",
                    y="Hours",
                    color="Status",
                    hover_data=["Day", "Min Hours", "Missing Hours", "Tasks"],
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

                # Task Analysis
                st.subheader("Task Analysis")
                all_tasks = [task for tasks in df["Tasks"] for task in tasks]
                task_counts = pd.Series(all_tasks).value_counts()
                fig_tasks = px.pie(
                    values=task_counts.values,
                    names=task_counts.index,
                    title="Task Distribution",
                )
                st.plotly_chart(fig_tasks, use_container_width=True)

                # Detailed table
                st.subheader("Detailed Work Log")

                # Function to apply color to Status column
                def color_status(row):
                    return [
                        "background-color: yellow" if row.Status == "Warning" else ""
                        for _ in row
                    ]

                # Apply styling
                styled_df = df.style.apply(color_status, axis=1)

                # Create a new DataFrame with the styled data and an additional column for the button
                df["TimeCamp Link"] = df["Date"].apply(
                    lambda x: f'<a href="https://app.timecamp.com/app#/timesheets/timer/{x.strftime("%Y-%m-%d")}" target="_blank"><button>View in TimeCamp</button></a>'
                )

                # Display the DataFrame with the new button column
                st.write(
                    styled_df.format(
                        {
                            "Date": lambda x: x.strftime("%Y-%m-%d"),
                            "Hours": "{:.2f}",
                            "Min Hours": "{:.2f}",
                            "Missing Hours": "{:.2f}",
                        }
                    )
                    .set_table_styles(
                        [
                            {
                                "selector": "th",
                                "props": [
                                    ("font-size", "110%"),
                                    ("text-align", "center"),
                                ],
                            }
                        ]
                    )
                    .to_html(escape=False),
                    unsafe_allow_html=True,
                )

            else:
                st.error(
                    "Failed to fetch data. Please check your API key and try again."
                )


if __name__ == "__main__":
    main()
