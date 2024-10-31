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
        color: black !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600)
def get_israeli_holidays(year):
    il_holidays = holidays.IL(years=year)
    return {
        date.strftime("%Y-%m-%d"): name for date, name in il_holidays.items()
    }


def is_holiday_eve(date, il_holidays):
    """Check if the given date is a holiday eve"""
    next_day = date + timedelta(days=1)
    next_day_str = next_day.strftime("%Y-%m-%d")
    return next_day_str in il_holidays


def get_required_hours(date, il_holidays):
    """Determine required work hours based on day and holiday status"""
    date_str = date.strftime("%Y-%m-%d")
    weekday = date.weekday()

    # Friday (4) and Saturday (5) - no work
    if weekday in {4, 5}:
        return 0

    # Check if it's a holiday
    if date_str in il_holidays:
        return 0

    # Check if it's a holiday eve
    if is_holiday_eve(date, il_holidays):
        return 7.5

    # Thursday (3)
    if weekday == 3:
        return 8

    # Sunday (6) to Wednesday (2)
    return 8.5


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
        first_day + timedelta(days=i)
        for i in range((last_day - first_day).days + 1)
    ]

    # Get Israeli holidays for the selected year
    il_holidays = get_israeli_holidays(year)

    results = []

    for date in date_range:
        # Check required hours for this date
        required_hours = get_required_hours(date, il_holidays)

        # Only fetch data if work is required on this day
        if required_hours > 0:
            work_hours, tasks = get_work_hours_and_tasks(api_key, date)
            results.append((date, work_hours, tasks, required_hours))

    if results:
        df = pd.DataFrame(
            results, columns=["Date", "Hours", "Tasks", "Required Hours"]
        )
        df["Date"] = pd.to_datetime(df["Date"])
        df["Day"] = df["Date"].dt.day_name()

        # Apply running balance calculations
        df = df.sort_values("Date")

        # Calculate daily difference (actual - required)
        df["Daily Difference"] = df["Hours"].fillna(0) - df["Required Hours"]

        # Calculate running balance and target
        df["Running Balance"] = df["Daily Difference"].cumsum()
        df["Target Balance"] = -df[
            "Required Hours"
        ].cumsum()  # Negative because we start at 0 and accumulate required hours

        # Update status based on running balance
        df["Status"] = df.apply(
            lambda row: (
                "OK"
                if (
                    pd.notnull(row["Hours"])
                    and (
                        (
                            row["Running Balance"] >= row["Target Balance"]
                            and row["Hours"] <= 11.5
                        )
                        or (
                            row["Running Balance"] < row["Target Balance"]
                            and row["Hours"] >= row["Required Hours"]
                        )
                    )
                )
                else "Warning"
            ),
            axis=1,
        )

        # Calculate missing hours only for the final day if running balance is below target
        df["Missing Hours"] = 0  # Initialize all days to 0
        final_gap = (
            df["Running Balance"].iloc[-1] - df["Target Balance"].iloc[-1]
        )
        if final_gap < 0:
            df.loc[df.index[-1], "Missing Hours"] = abs(final_gap)

        return df, il_holidays
    return pd.DataFrame(), il_holidays


def get_work_hours_and_tasks(api_key, date):
    url = "https://app.timecamp.com/third_party/api/entries"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
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


def calculate_running_balance(df):
    """Calculate running balance of work hours"""
    df = df.sort_values("Date")

    # Calculate daily difference (actual - required)
    df["Daily Difference"] = df["Hours"].fillna(0) - df["Required Hours"]

    # Calculate running balance
    df["Running Balance"] = df["Daily Difference"].cumsum()

    # Update status based on running balance
    df["Status"] = df.apply(
        lambda row: (
            "OK"
            if (
                pd.notnull(row["Hours"])
                and (
                    (row["Running Balance"] >= 0 and row["Hours"] <= 11.5)
                    or (
                        row["Running Balance"] < 0
                        and row["Hours"] >= row["Required Hours"]
                    )
                )
            )
            else "Warning"
        ),
        axis=1,
    )

    # Recalculate missing hours considering running balance
    df["Missing Hours"] = df.apply(
        lambda row: (
            abs(row["Running Balance"])
            if row["Running Balance"] < 0 and row["Date"] == row["Date"].max()
            else 0
        ),
        axis=1,
    )

    return df


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
            formatted_date = datetime.strptime(date, "%Y-%m-%d").strftime(
                "%d %B"
            )
            st.markdown(
                f'<div class="holiday-item">🗓 {formatted_date}: {holiday_name}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info(
            f"There are no holidays in {calendar.month_name[month]} {year}."
        )


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
        start_date = st.sidebar.date_input(
            "Start date", datetime(year, month, 1)
        )
        end_date = st.sidebar.date_input("End date", datetime(year, month, 28))

    fetch_button = st.sidebar.button("Fetch Data")
    if not fetch_button:
        st.markdown(
            """
        <div class="api-instructions">
            <h3>How to Get Your TimeCamp API Key</h3>
            <div class="instruction-step">1. Log in to your TimeCamp account at <a href="https://app.timecamp.com" target="_blank">app.timecamp.com</a></div>
            <div class="instruction-step">2. Click on your profile picture in the top-right corner</div>
            <div class="instruction-step">3. Select "Profile Settings" from the dropdown menu</div>
            <div class="instruction-step">4. Scroll down to "Your programming API token"</div>
            <div class="instruction-step">5. Copy your API token</div>
            <div class="instruction-step">6. Paste the token in the API Key field in the sidebar</div>
            <br>
            <em>Note: Your API key is stored securely and is only used to fetch your time entries from TimeCamp.</em>
        </div>
        """,
            unsafe_allow_html=True,
        )

    if fetch_button:
        if not api_key:
            st.sidebar.error("Please enter an API key.")
        else:
            with st.spinner("Fetching data..."):
                if use_custom_date:
                    df, il_holidays = fetch_data(
                        api_key, start_date.year, start_date.month
                    )
                    df = df[
                        (df["Date"].dt.date >= start_date)
                        & (df["Date"].dt.date <= end_date)
                    ]
                else:
                    df, il_holidays = fetch_data(api_key, year, month)

            # Display holidays for the selected month
            display_holidays(il_holidays, year, month)

            if not df.empty:
                # Summary statistics with running balance
                total_hours = df["Hours"].sum()
                final_balance = df["Running Balance"].iloc[-1]
                missing_hours = abs(final_balance) if final_balance < 0 else 0
                warning_days = df[df["Status"] == "Warning"].shape[0]

                # Display metrics
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Total Hours Worked", f"{total_hours:.2f}")
                with col2:
                    st.metric(
                        "Running Balance",
                        f"{final_balance:.2f}",
                        delta=f"{final_balance:.2f}",
                        delta_color="normal",
                    )
                with col3:
                    st.metric("Missing Hours", f"{missing_hours:.2f}")
                with col4:
                    st.metric("Days with Warnings", warning_days)
                with col5:
                    avg_hours_per_day = total_hours / len(df)
                    st.metric(
                        "Average Hours per Day", f"{avg_hours_per_day:.2f}"
                    )

                # Display detailed table with running balance
                st.subheader("Detailed Work Log")

                def color_status(row):
                    return [
                        (
                            "background-color: yellow"
                            if row.Status == "Warning"
                            else ""
                        )
                        for _ in row
                    ]

                display_columns = [
                    "Date",
                    "Day",
                    "Hours",
                    "Required Hours",
                    "Daily Difference",
                    "Running Balance",
                    "Status",
                    "Tasks",
                ]

                styled_df = df[display_columns].style.apply(
                    color_status, axis=1
                )

                # Add TimeCamp link
                df["TimeCamp Link"] = df["Date"].apply(
                    lambda x: f'<a href="https://app.timecamp.com/app#/timesheets/timer/{x.strftime("%Y-%m-%d")}" target="_blank"><button>View in TimeCamp</button></a>'
                )

                st.write(
                    styled_df.format(
                        {
                            "Date": lambda x: x.strftime("%Y-%m-%d"),
                            "Hours": "{:.2f}",
                            "Required Hours": "{:.2f}",
                            "Daily Difference": "{:.2f}",
                            "Running Balance": "{:.2f}",
                        }
                    ).to_html(escape=False),
                    unsafe_allow_html=True,
                )

                # Visualizations
                st.subheader(
                    f"Daily Work Hours for {calendar.month_name[month]} {year}"
                )

                # Hours bar chart
                fig1 = px.bar(
                    df,
                    x="Date",
                    y="Hours",
                    color="Status",
                    hover_data=[
                        "Day",
                        "Required Hours",
                        "Running Balance",
                        "Tasks",
                    ],
                    labels={"Hours": "Work Hours"},
                    color_discrete_map={"OK": "green", "Warning": "red"},
                )
                fig1.add_scatter(
                    x=df["Date"],
                    y=df["Required Hours"],
                    mode="lines",
                    name="Required Hours",
                    line=dict(color="blue", dash="dash"),
                )
                st.plotly_chart(fig1, use_container_width=True)


            else:
                st.error(
                    "Failed to fetch data. Please check your API key and try again."
                )


if __name__ == "__main__":
    main()
