import re
import pandas as pd
import streamlit as st
import plotly.express as px

# ============================================================
# Streamlit page setup and client-facing styling
# ============================================================

st.set_page_config(
    page_title="Campion EdTech Adoption Insights",
    layout="wide"
)

st.markdown(
    """
    <style>
    .main { background-color: #fafafa; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #1f2937; }
    .campion-hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
        padding: 2rem 2.2rem;
        border-radius: 18px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .campion-hero h1 {
        color: white;
        font-size: 2.2rem;
        margin-bottom: 0.4rem;
    }
    .campion-hero p {
        color: #e5e7eb;
        font-size: 1.05rem;
        margin-bottom: 0;
    }
    .section-note {
        color: #4b5563;
        font-size: 1rem;
        line-height: 1.5;
    }
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #e5e7eb;
        padding: 1rem;
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
    }
    section[data-testid="stSidebar"] { background-color: #f8fafc; }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <div class="campion-hero">
        <h1>Campion EdTech Adoption Insights Dashboard</h1>
        <p>
            An interactive view of how Australian schools are using, evaluating,
            and planning for educational technology and generative AI.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

# Keep the main section navigation directly under the dashboard header.
tab_profile, tab_tool_use, tab_satisfaction, tab_adoption, tab_interactions, tab_admin = st.tabs(
    [
        "Executive Overview",
        "Current EdTech Use",
        "Satisfaction & Value",
        "Adoption Priorities",
        "Strategic Segments",
        "Admin / Data Quality"
    ]
)


# ============================================================
# Cleaning helpers
# ============================================================

def clean_column_name(x):
    x = str(x).strip().lower()
    x = re.sub(r"\s+", "_", x)
    x = re.sub(r"[^a-z0-9_]+", "", x)
    x = re.sub(r"_+", "_", x)
    return x.strip("_")


def make_unique(columns):
    seen = {}
    unique_cols = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            unique_cols.append(col)
        else:
            seen[col] += 1
            unique_cols.append(f"{col}_{seen[col]}")
    return unique_cols


def clean_two_header_excel(uploaded_file, sheet_name=0, missing_threshold=80):
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    header_1 = raw.iloc[0]
    header_2 = raw.iloc[1]
    data = raw.iloc[2:].copy()

    new_columns = []
    for h1, h2 in zip(header_1, header_2):
        if pd.notna(h1) and pd.notna(h2):
            col_name = f"{h1}_{h2}"
        elif pd.notna(h1):
            col_name = h1
        elif pd.notna(h2):
            col_name = h2
        else:
            col_name = "unnamed"
        new_columns.append(clean_column_name(col_name))

    data.columns = make_unique(new_columns)
    data = data.dropna(axis=0, how="all")
    data = data.dropna(axis=1, how="all")

    pii_keywords = [
        "ip_address", "email", "first_name", "last_name", "school_name",
        "collector_id", "recipient", "custom_data"
    ]
    cols_to_drop = [
        col for col in data.columns
        if any(keyword in col for keyword in pii_keywords)
    ]
    data = data.drop(columns=cols_to_drop, errors="ignore")

    row_missing_percent = data.isna().mean(axis=1) * 100
    data_clean = data.loc[row_missing_percent <= missing_threshold].copy()
    data_clean = data_clean.reset_index(drop=True)

    if "respondent_id_anon" not in data_clean.columns:
        data_clean.insert(0, "respondent_id_anon", [f"R{i+1:03d}" for i in range(len(data_clean))])

    return data_clean, raw, cols_to_drop


# ============================================================
# Matching helpers
# ============================================================

def norm_text(x):
    return (
        str(x).lower()
        .replace("&", "")
        .replace("/", "")
        .replace("-", "")
        .replace("—", "")
        .replace("–", "")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
        .replace("'", "")
        .replace(" ", "")
        .replace("_", "")
        .strip()
    )


def find_first_existing_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def find_column_by_keywords(df, include_terms, exclude_terms=None):
    if exclude_terms is None:
        exclude_terms = []
    include_terms_norm = [norm_text(term) for term in include_terms]
    exclude_terms_norm = [norm_text(term) for term in exclude_terms]
    matches = []
    for col in df.columns:
        col_norm = norm_text(col)
        if all(term in col_norm for term in include_terms_norm):
            if not any(term in col_norm for term in exclude_terms_norm):
                matches.append(col)
    return matches


def find_best_column(df, include_terms, exclude_terms=None):
    matches = find_column_by_keywords(df, include_terms, exclude_terms)
    return matches[0] if matches else None


# ============================================================
# Generic plotting helpers
# ============================================================

def plot_categorical_variable(df, col, title, x_title, chart_type="Bar - Percentage", horizontal=False, category_order=None):
    summary = df[col].fillna("Missing").value_counts().reset_index()
    summary.columns = ["category", "count"]
    summary["percent"] = summary["count"] / summary["count"].sum() * 100

    if category_order is not None:
        summary["category"] = pd.Categorical(summary["category"], categories=category_order, ordered=True)
        summary = summary.sort_values("category")
    else:
        summary = summary.sort_values("percent", ascending=False)

    if chart_type == "Pie":
        fig = px.pie(summary, names="category", values="count", title=title, hole=0.35)
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>"
        )
        fig.update_layout(template="plotly_white", height=500)
        return fig

    if chart_type == "Bar - Count":
        y_col = "count"
        y_label = "Number of Respondents"
        text_values = summary["count"].astype(str)
    else:
        y_col = "percent"
        y_label = "Percentage of Respondents"
        text_values = summary["percent"].round(1).astype(str) + "%"

    if horizontal:
        summary = summary.sort_values(y_col)
        fig = px.bar(
            summary,
            y="category",
            x=y_col,
            orientation="h",
            title=title,
            labels={"category": x_title, y_col: y_label},
            text=text_values
        )
        fig.update_traces(
            textposition="inside",
            customdata=summary[["count", "percent"]],
            hovertemplate="<b>%{y}</b><br>Count: %{customdata[0]}<br>Percentage: %{customdata[1]:.1f}%<extra></extra>"
        )
        fig.update_layout(template="plotly_white", height=500, xaxis_title=y_label, yaxis_title=x_title)
    else:
        fig = px.bar(
            summary,
            x="category",
            y=y_col,
            title=title,
            labels={"category": x_title, y_col: y_label},
            text=text_values
        )
        fig.update_traces(
            textposition="inside",
            customdata=summary[["count", "percent"]],
            hovertemplate="<b>%{x}</b><br>Count: %{customdata[0]}<br>Percentage: %{customdata[1]:.1f}%<extra></extra>"
        )
        fig.update_layout(template="plotly_white", height=500, xaxis_tickangle=-25, xaxis_title=x_title, yaxis_title=y_label)

    return fig


def plot_crosstab_percent(df, row_col, col_col, row_label, col_label, title, chart_type="Heatmap"):
    temp = df[[row_col, col_col]].copy().fillna("Missing")
    ctab = pd.crosstab(temp[row_col], temp[col_col], normalize="index") * 100
    count_tab = pd.crosstab(temp[row_col], temp[col_col])

    if chart_type == "Heatmap":
        fig = px.imshow(
            ctab,
            text_auto=".1f",
            aspect="auto",
            title=title,
            labels={"x": col_label, "y": row_label, "color": "% within row"}
        )
        fig.update_layout(template="plotly_white", height=600, margin=dict(t=80, b=80, l=220, r=40))
        fig.update_xaxes(tickangle=-25)
        return fig

    long_df = ctab.reset_index().melt(id_vars=row_col, var_name=col_label, value_name="percent")
    count_long = count_tab.reset_index().melt(id_vars=row_col, var_name=col_label, value_name="count")
    long_df = long_df.merge(count_long, on=[row_col, col_label], how="left")

    fig = px.bar(
        long_df,
        x=row_col,
        y="percent",
        color=col_label,
        barmode="group",
        title=title,
        labels={row_col: row_label, "percent": "% within group", col_label: col_label},
        custom_data=["count"]
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Category: %{fullData.name}<br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=600, xaxis_tickangle=-25)
    return fig


# ============================================================
# Tool-use helpers for Q7-Q14
# ============================================================

tool_specs = {
    "Productivity & organisation tools": "productivity_organisation_tools",
    "School platforms & content systems": "school_platforms_content_systems",
    "Teaching & learning tools": "teaching_learning_tools_purposebuilt_edtech",
    "GenAI — general purpose": "generative_ai_general_purpose",
    "GenAI — education-specific": "generative_ai_educational_specific",
}

tool_label_map = {
    "Productivity & organisation tools": "Productivity /\norganisation",
    "School platforms & content systems": "School platforms /\ncontent systems",
    "Teaching & learning tools": "Teaching &\nlearning tools",
    "GenAI — general purpose": "GenAI:\ngeneral",
    "GenAI — education-specific": "GenAI:\neducation-specific"
}

color_map = {
    "Productivity & organisation tools": "#1f77b4",
    "School platforms & content systems": "#ff7f0e",
    "Teaching & learning tools": "#2ca02c",
    "GenAI — general purpose": "#9467bd",
    "GenAI — education-specific": "#d62728"
}

stage_tasks = {
    "Planning": {
        "Define learning objectives": "define_learning_objectives",
        "Plan curriculum content and sequencing": "plan_curriculum_content_and_sequencing",
        "Plan and sequence lessons": "plan_and_sequence_lessons",
    },
    "Preparation": {
        "Generate or adapt lesson plans": "generate_or_adapt_lesson_plans",
        "Create or source teaching resources": "create_or_source_teaching_resources",
        "Personalise materials for different learners": "personalise_materials_for_different_learners",
        "Design assessments and rubrics": "design_assessments_and_rubrics",
    },
    "Teaching": {
        "Deliver lessons": "deliver_lessons",
        "Adapt delivery to student understanding in real time": "adapt_delivery_to_student_understanding_in_real_time",
        "Support students with additional learning needs": "support_students_with_additional_learning_needs",
        "Manage classroom behaviour and environment": "manage_classroom_behaviour_and_environment",
    },
    "Practice and Application": {
        "Design practice tasks for independent or in-class work": "design_practice_tasks_for_independent_or_inclass_work",
        "Set and manage homework": "set_and_manage_homework",
        "Facilitate collaborative activities": "facilitate_collaborative_activities",
        "Provide access to subject-specific tools or simulations": "provide_access_to_subjectspecific_tools_or_simulations",
    },
    "Assessment": {
        "Deliver summative assessments": "deliver_summative_assessments",
        "Deliver formative assessments": "deliver_formative_assessments",
        "Assess student process, not just outputs": "assess_student_process_not_just_outputs",
        "Facilitate self and/or peer assessment": "facilitate_self_andor_peer_assessment",
        "Mark and grade student work": "mark_and_grade_student_work",
        "Moderation": "moderation",
        "Support academic integrity": "support_academic_integrity",
    },
    "Feedback and Intervention": {
        "Create written feedback": "create_written_feedback",
        "Deliver feedback to students": "deliver_feedback_to_students",
        "Support students to act on feedback": "support_students_to_act_on_feedback",
        "Plan and manage interventions": "plan_and_manage_interventions",
    },
    "Monitoring and Progress": {
        "Track student progress over time": "track_student_progress_over_time",
        "Monitor the effectiveness of teaching": "monitor_the_effectiveness_of_teaching",
        "Identify students at risk": "identify_students_at_risk",
    },
    "Wellbeing": {
        "Monitor student wellbeing": "monitor_student_wellbeing",
        "Provide support to students and/or parents": "provide_support_to_students_andor_parents",
        "Track pastoral support for students": "track_pastoral_support_for_students",
    },
}


def find_matrix_col(df, task_stem, tool_key):
    task_norm = norm_text(task_stem)
    tool_norm = norm_text(tool_key)
    matches = []
    for col in df.columns:
        col_norm = norm_text(col)
        if task_norm in col_norm and tool_norm in col_norm:
            matches.append(col)
    return matches[0] if matches else None


def make_stage_summary(df, stage_name, tasks):
    records = []
    missing_cols = []
    matrix_cols = []

    for task_label, task_stem in tasks.items():
        for tool_label, tool_key in tool_specs.items():
            col = find_matrix_col(df, task_stem, tool_key)
            if col is None:
                missing_cols.append({
                    "stage": stage_name,
                    "task": task_label,
                    "tool_type": tool_label,
                    "task_stem": task_stem,
                    "tool_key": tool_key
                })
                continue

            matrix_cols.append(col)
            selected = df[col].notna() & (df[col] != 0)
            records.append({
                "stage": stage_name,
                "task": task_label,
                "tool_type": tool_label,
                "column": col,
                "count": int(selected.sum())
            })

    if len(matrix_cols) == 0:
        return pd.DataFrame(), pd.DataFrame(missing_cols), 0

    summary = pd.DataFrame(records)
    answered_stage = (df[matrix_cols].notna() & (df[matrix_cols] != 0)).any(axis=1)
    n_answered = int(answered_stage.sum())
    summary["n_stage_respondents"] = n_answered
    summary["percent_stage_respondents"] = summary["count"] / n_answered * 100 if n_answered > 0 else 0
    return summary, pd.DataFrame(missing_cols), n_answered


def plot_stage_facets(summary, stage_name, facet_wrap=2, height=800):
    plot_df = summary.copy()
    plot_df["tool_label"] = plot_df["tool_type"].replace(tool_label_map)

    fig = px.bar(
        plot_df,
        x="tool_label",
        y="percent_stage_respondents",
        color="tool_type",
        color_discrete_map=color_map,
        facet_col="task",
        facet_col_wrap=facet_wrap,
        title=f"{stage_name}: EdTech Product Use by Task",
        labels={
            "tool_label": "EdTech Product Type",
            "percent_stage_respondents": f"Percentage of {stage_name} Respondents",
            "tool_type": "EdTech Product Type"
        },
        text=plot_df["percent_stage_respondents"].round(1).astype(str) + "%",
        custom_data=["count", "tool_type", "n_stage_respondents"]
    )
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{customdata[1]}</b><br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<br>Stage respondents: %{customdata[2]}<extra></extra>"
    )
    y_max = plot_df["percent_stage_respondents"].max()
    fig.update_layout(
        template="plotly_white",
        height=height,
        yaxis_title=f"Percentage of {stage_name} Respondents",
        legend_title="EdTech Product Type",
        margin=dict(t=90, b=50, l=60, r=40)
    )
    fig.update_xaxes(tickangle=0, title_text="")
    fig.update_yaxes(range=[0, max(10, y_max + 10)])
    fig.for_each_annotation(lambda a: a.update(text=a.text.replace("task=", "")))
    return fig


def plot_stage_heatmap(summary, stage_name):
    heatmap_data = summary.pivot(index="task", columns="tool_type", values="percent_stage_respondents").fillna(0)
    ordered_tools = list(tool_specs.keys())
    existing_tools = [tool for tool in ordered_tools if tool in heatmap_data.columns]
    heatmap_data = heatmap_data[existing_tools]
    fig = px.imshow(
        heatmap_data,
        text_auto=".1f",
        aspect="auto",
        title=f"{stage_name}: EdTech Product Use Heatmap",
        labels={"x": "EdTech Product Type", "y": "Task", "color": "% of Stage Respondents"}
    )
    fig.update_layout(template="plotly_white", height=500, margin=dict(t=80, b=60, l=250, r=40))
    fig.update_xaxes(tickangle=-25)
    return fig


def plot_stage_grouped_bar(summary, stage_name):
    fig = px.bar(
        summary,
        x="task",
        y="percent_stage_respondents",
        color="tool_type",
        color_discrete_map=color_map,
        barmode="group",
        title=f"{stage_name}: EdTech Product Use by Task",
        labels={
            "task": "Task",
            "percent_stage_respondents": "Percentage of Stage Respondents",
            "tool_type": "EdTech Product Type"
        },
        custom_data=["count", "tool_type", "n_stage_respondents"]
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Tool type: %{customdata[1]}<br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<br>Stage respondents: %{customdata[2]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=650, xaxis_tickangle=-25, legend_title="EdTech Product Type")
    return fig


def make_stage_summary_by_group(df, stage_name, tasks, group_col):
    records = []
    for group_value, group_df in df.groupby(group_col, dropna=False):
        group_label = "Missing" if pd.isna(group_value) else str(group_value)
        summary, _, n_answered = make_stage_summary(group_df, stage_name, tasks)
        if summary.empty:
            continue
        summary["group_variable"] = group_col
        summary["group_value"] = group_label
        summary["group_n_stage_respondents"] = n_answered
        records.append(summary)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def plot_tool_use_by_group(group_summary, stage_name, group_label, chart_type="Faceted grouped bar chart"):
    plot_df = group_summary.copy()

    if chart_type == "Heatmap":
        heat = plot_df.groupby(["group_value", "tool_type"], as_index=False).agg(
            mean_percent=("percent_stage_respondents", "mean")
        )
        heatmap_data = heat.pivot(index="group_value", columns="tool_type", values="mean_percent").fillna(0)
        ordered_tools = list(tool_specs.keys())
        existing_tools = [tool for tool in ordered_tools if tool in heatmap_data.columns]
        heatmap_data = heatmap_data[existing_tools]
        fig = px.imshow(
            heatmap_data,
            text_auto=".1f",
            aspect="auto",
            title=f"{stage_name}: Average Tool Use by {group_label}",
            labels={"x": "Tool Type", "y": group_label, "color": "Mean % across tasks"}
        )
        fig.update_layout(template="plotly_white", height=600, margin=dict(t=80, b=80, l=220, r=40))
        fig.update_xaxes(tickangle=-25)
        return fig

    fig = px.bar(
        plot_df,
        x="group_value",
        y="percent_stage_respondents",
        color="tool_type",
        color_discrete_map=color_map,
        facet_col="task",
        facet_col_wrap=2,
        barmode="group",
        title=f"{stage_name}: EdTech Product Use by {group_label}",
        labels={
            "group_value": group_label,
            "percent_stage_respondents": "% of Stage Respondents",
            "tool_type": "EdTech Product Type"
        },
        custom_data=["count", "group_n_stage_respondents"]
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Tool type: %{fullData.name}<br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<br>Group stage respondents: %{customdata[1]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=900, xaxis_tickangle=-25, legend_title="EdTech Product Type")
    fig.for_each_annotation(lambda a: a.update(text=a.text.replace("task=", "")))
    return fig


# ============================================================
# Q15 satisfaction helpers
# ============================================================

tool_order = list(tool_specs.keys())


def find_q15_columns(df):
    q15_start_matches = [
        col for col in df.columns
        if "thinking_about_your_use_of_edtech_tools_across_the_teaching_journey" in col
        and "satisfaction" in col
        and "productivity_organisation_tools" in col
    ]
    if len(q15_start_matches) == 0:
        q15_start_matches = [
            col for col in df.columns
            if "satisfaction" in col and "productivity" in col and "organisation" in col
        ]
    if len(q15_start_matches) == 0:
        return {}
    start_col = q15_start_matches[0]
    start_idx = list(df.columns).index(start_col)
    q15_cols_in_order = list(df.columns[start_idx:start_idx + 5])
    if len(q15_cols_in_order) < 5:
        return {}
    return {
        "Productivity & organisation tools": q15_cols_in_order[0],
        "School platforms & content systems": q15_cols_in_order[1],
        "Teaching & learning tools": q15_cols_in_order[2],
        "GenAI — general purpose": q15_cols_in_order[3],
        "GenAI — education-specific": q15_cols_in_order[4],
    }


def make_q15_long(df, q15_cols):
    q15_long = []
    for tool_type, col in q15_cols.items():
        temp = df[[col]].copy().rename(columns={col: "satisfaction_raw"})
        temp["tool_type"] = tool_type
        temp["satisfaction_score"] = temp["satisfaction_raw"].astype(str).str.extract(r"(\d+)").astype(float)
        q15_long.append(temp)
    if not q15_long:
        return pd.DataFrame()
    q15_long = pd.concat(q15_long, ignore_index=True)
    q15_long = q15_long.dropna(subset=["satisfaction_score"])
    q15_long["satisfaction_score"] = q15_long["satisfaction_score"].astype(int)
    q15_long = q15_long[q15_long["satisfaction_score"].between(1, 10)].copy()
    return q15_long


def plot_q15_mean(q15_long):
    q15_summary = q15_long.groupby("tool_type", as_index=False).agg(
        mean_satisfaction=("satisfaction_score", "mean"),
        median_satisfaction=("satisfaction_score", "median"),
        n=("satisfaction_score", "count")
    )
    q15_summary["tool_type"] = pd.Categorical(q15_summary["tool_type"], categories=tool_order, ordered=True)
    q15_summary = q15_summary.sort_values("tool_type")
    q15_summary["mean_label"] = q15_summary["mean_satisfaction"].round(1).astype(str)
    fig = px.bar(
        q15_summary,
        x="tool_type",
        y="mean_satisfaction",
        title="Average Satisfaction by EdTech Product Category",
        labels={"tool_type": "Tool Type", "mean_satisfaction": "Mean Satisfaction Score"},
        text="mean_label",
        custom_data=["median_satisfaction", "n"]
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Mean: %{y:.2f}<br>Median: %{customdata[0]}<br>Responses: %{customdata[1]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=550, yaxis=dict(range=[0, 10], dtick=1), xaxis_tickangle=-25)
    return fig, q15_summary


def plot_q15_heatmap(q15_long):
    q15_dist = q15_long.groupby(["tool_type", "satisfaction_score"]).size().reset_index(name="count")
    q15_dist["total_for_tool"] = q15_dist.groupby("tool_type")["count"].transform("sum")
    q15_dist["percent"] = q15_dist["count"] / q15_dist["total_for_tool"] * 100
    q15_dist["score_label"] = q15_dist["satisfaction_score"].astype(str)
    heatmap_data = q15_dist.pivot(index="tool_type", columns="score_label", values="percent").fillna(0)
    heatmap_data = heatmap_data.reindex(tool_order)
    for score in [str(i) for i in range(1, 11)]:
        if score not in heatmap_data.columns:
            heatmap_data[score] = 0
    heatmap_data = heatmap_data[[str(i) for i in range(1, 11)]]
    fig = px.imshow(
        heatmap_data,
        text_auto=".1f",
        aspect="auto",
        title="Satisfaction Distribution by EdTech Product Category",
        labels={"x": "Satisfaction Score", "y": "Tool Type", "color": "% of Responses"}
    )
    fig.update_layout(template="plotly_white", height=500, margin=dict(t=80, b=60, l=220, r=40))
    return fig, q15_dist


def plot_q15_box(q15_long):
    fig = px.box(
        q15_long,
        x="tool_type",
        y="satisfaction_score",
        points="all",
        title="Satisfaction Score Spread by EdTech Product Category",
        labels={"tool_type": "Tool Type", "satisfaction_score": "Satisfaction Score"},
        category_orders={"tool_type": tool_order}
    )
    fig.update_layout(template="plotly_white", height=600, yaxis=dict(range=[0, 10], dtick=1), xaxis_tickangle=-25)
    return fig


def plot_satisfaction_by_group(df, group_col, group_label, q15_cols):
    records = []
    for tool_type, score_col in q15_cols.items():
        temp = df[[group_col, score_col]].copy().rename(columns={score_col: "satisfaction_raw"})
        temp["tool_type"] = tool_type
        temp["satisfaction_score"] = temp["satisfaction_raw"].astype(str).str.extract(r"(\d+)").astype(float)
        temp = temp.dropna(subset=["satisfaction_score"])
        temp = temp[temp["satisfaction_score"].between(1, 10)]
        temp[group_col] = temp[group_col].fillna("Missing")
        records.append(temp)
    if not records:
        return None, pd.DataFrame()
    long_df = pd.concat(records, ignore_index=True)
    summary = long_df.groupby([group_col, "tool_type"], as_index=False).agg(
        mean_satisfaction=("satisfaction_score", "mean"),
        n=("satisfaction_score", "count")
    )
    fig = px.bar(
        summary,
        x=group_col,
        y="mean_satisfaction",
        color="tool_type",
        barmode="group",
        title=f"Mean Satisfaction by {group_label}",
        labels={group_col: group_label, "mean_satisfaction": "Mean Satisfaction Score", "tool_type": "Tool Type"},
        custom_data=["n"]
    )
    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Tool type: %{fullData.name}<br>Mean satisfaction: %{y:.2f}<br>Responses: %{customdata[0]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=650, yaxis=dict(range=[0, 10], dtick=1), xaxis_tickangle=-25)
    return fig, summary


# ============================================================
# School adoption and readiness helpers
# ============================================================

interest_order = [
    "Not at all interested", "Slightly interested", "Somewhat interested",
    "Moderately interested", "Very interested", "Extremely interested"
]

proficiency_order = [
    "No proficiency", "Beginner", "Developing", "Proficient",
    "Advanced (able to support or train others)"
]


def get_school_adoption_columns(df):
    cols = {}
    cols["expand_next_12_months"] = find_first_existing_col(df, [
        "thinking_about_your_total_school_needs_will_you_be_looking_to_develop_or_expand_your_use_of_educational_technology_in_the_next_12_monthsselect_one_response"
    ])
    cols["journey_interest"] = {
        "Planning and curriculum design": "in_which_parts_of_the_teaching_journey_is_your_school_most_interested_in_developing_or_expanding_its_use_of_edtech_planning_and_curriculum_design",
        "Lesson preparation and resource creation": "lesson_preparation_and_resource_creation",
        "Classroom teaching and delivery": "classroom_teaching_and_delivery",
        "Student practice and independent learning": "student_practice_and_independent_learning",
        "Assessment design and delivery": "assessment_design_and_delivery",
        "Feedback and intervention": "feedback_and_intervention",
        "Progress monitoring and reporting": "progress_monitoring_and_reporting",
        "Wellbeing": "wellbeing",
        "Staff professional development in EdTech": "staff_professional_development_in_edtech",
    }
    cols["tool_interest"] = {
        "Productivity & organisation tools": "which_types_of_tools_is_your_school_interested_in_adopting_or_expanding_if_already_implemented_in_the_next_12_months_productivity_organisation_tools",
        "School platforms & content systems": "school_platforms_content_systems_1",
        "Teaching & learning tools": "teaching_learning_tools_purposebuilt_edtech_1",
        "GenAI — general purpose": "generative_ai_general_purpose_1",
        "GenAI — education-specific": "generative_ai_educational_specific_1",
    }
    cols["training_policy"] = {
        "Training for teachers on EdTech use": "is_your_school_planning_to_support_this_expansion_with_training_and_policyselect_all_that_apply_training_for_teachers_on_edtech_use",
        "Training for teachers on generative AI use": "training_for_teachers_on_generative_ai_use",
        "Training for students on generative AI use": "training_for_students_on_generative_ai_use",
        "Creation/refresher of EdTech and GenAI policies": "creation_or_refreshing_of_policies_on_edtech_and_generative_ai",
    }
    cols["barriers"] = {
        "Time, workload and competing priorities": "what_are_the_main_barriers_to_developing_your_schools_use_of_digital_tools_and_technology_including_generative_aiselect_your_top_three_1_time_workload_and_competing_prioritieseg_not_enough_time_to_learn_trial_or_embed_new_digital_tools",
        "Funding and cost implications": "2_funding_and_cost_implicationseg_cost_and_limited_budgets",
        "Skills, confidence and professional learning gaps": "3_skills_confidence_and_professional_learning_gapseg_insufficient_training_or_uncertainty_about_how_to_use_tools_effectively",
        "Leadership, strategy and policy uncertainty": "4_leadership_strategy_and_policy_uncertaintyeg_lack_of_wholeschool_direction_leadership_support_or_clear_guidance_on_edtechai_use",
        "Risk or ethics concerns": "5_risk_or_ethics_concernseg_data_privacy_security_or_academic_integrity",
    }
    cols["formal_policies"] = {
        "EdTech use generally": "does_your_school_have_formal_policies_covering_any_of_the_followingselect_all_that_apply_edtech_use_generally",
        "Data privacy": "data_privacy",
        "Academic integrity": "academic_integrity",
        "Generative AI use by staff": "generative_ai_use_by_staff",
        "Generative AI use by students": "generative_ai_use_by_students",
        "No formal policies": "my_school_has_no_formal_policies_in_this_area",
        "Don’t know": "i_dont_know_what_policies_my_school_has_in_place",
    }
    cols["genai_proficiency"] = {
        "Understanding what GenAI is and how it works": "how_would_you_rate_your_current_level_of_proficiency_in_each_of_the_following_areas_of_generative_aifor_each_row_select_one_no_proficiency_beginner_developing_proficient_advanced_able_to_support_or_train_others_understanding_what_generative_ai_is_and_how_it_works",
        "Using GenAI tools effectively": "using_generative_ai_tools_effectively_in_my_professional_role",
        "Using GenAI tools responsibly and ethically": "using_generative_ai_tools_responsibly_and_ethically",
        "Identifying appropriate AI tools for education": "identifying_which_ai_tools_are_appropriate_for_use_in_education",
        "Understanding ethics and safeguarding": "understanding_ethics_and_safeguarding_when_using_ai_with_students",
        "Supporting students to use AI effectively": "supporting_students_to_use_ai_effectively_and_responsibly",
    }
    cols["future_genai_use"] = find_first_existing_col(df, [
        "thinking_about_the_next_12_months_how_do_you_expect_your_use_of_generative_ai_in_your_professional_role_to_changeselect_one_response"
    ])
    return cols


def make_likert_long(df, col_map, value_order=None):
    records = []
    for item, col in col_map.items():
        if col not in df.columns:
            continue
        temp = df[col].dropna().value_counts().reset_index()
        temp.columns = ["response", "count"]
        temp["item"] = item
        temp["total"] = temp["count"].sum()
        temp["percent"] = temp["count"] / temp["total"] * 100
        records.append(temp)
    if not records:
        return pd.DataFrame()
    out = pd.concat(records, ignore_index=True)
    if value_order is not None:
        out["response"] = pd.Categorical(out["response"], categories=value_order, ordered=True)
        out = out.sort_values(["item", "response"])
    return out


def plot_likert_heatmap(likert_df, title):
    heatmap_data = likert_df.pivot(index="item", columns="response", values="percent").fillna(0)
    fig = px.imshow(
        heatmap_data,
        text_auto=".1f",
        aspect="auto",
        title=title,
        labels={"x": "Response", "y": "", "color": "% of Responses"}
    )
    fig.update_layout(template="plotly_white", height=max(450, 55 * len(heatmap_data)), margin=dict(t=80, b=80, l=280, r=40))
    fig.update_xaxes(tickangle=-30)
    return fig


def plot_likert_stacked_bar(likert_df, title):
    fig = px.bar(
        likert_df,
        y="item",
        x="percent",
        color="response",
        orientation="h",
        title=title,
        labels={"item": "", "percent": "Percentage of Responses", "response": "Response"},
        custom_data=["count", "total"]
    )
    fig.update_traces(
        hovertemplate="<b>%{y}</b><br>Response: %{fullData.name}<br>Percentage: %{x:.1f}%<br>Count: %{customdata[0]} / %{customdata[1]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=max(500, 55 * likert_df["item"].nunique()), barmode="stack", margin=dict(t=80, b=60, l=280, r=40))
    return fig


def make_multiselect_summary(df, col_map):
    records = []
    for item, col in col_map.items():
        if col not in df.columns:
            continue
        selected = df[col].notna() & (df[col] != 0)
        records.append({"item": item, "count": int(selected.sum()), "percent": selected.mean() * 100})
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values("percent", ascending=True)


def plot_multiselect_bar(summary, title):
    fig = px.bar(
        summary,
        y="item",
        x="percent",
        orientation="h",
        title=title,
        labels={"item": "", "percent": "Percentage of Respondents"},
        text=summary["percent"].round(1).astype(str) + "%",
        custom_data=["count"]
    )
    fig.update_traces(
        textposition="inside",
        hovertemplate="<b>%{y}</b><br>Percentage: %{x:.1f}%<br>Count: %{customdata[0]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=max(450, 55 * len(summary)), margin=dict(t=80, b=60, l=280, r=40))
    return fig


def build_adoption_interaction_vars(df, adoption_cols):
    adoption_vars = {}
    if adoption_cols["expand_next_12_months"] is not None:
        col = adoption_cols["expand_next_12_months"]
        if col in df.columns:
            adoption_vars["Expansion plans: next 12 months"] = col
    if adoption_cols["future_genai_use"] is not None:
        col = adoption_cols["future_genai_use"]
        if col in df.columns:
            adoption_vars["Expected future GenAI use"] = col
    for label, col in adoption_cols["journey_interest"].items():
        if col in df.columns:
            adoption_vars[f"Journey expansion interest: {label}"] = col
    for label, col in adoption_cols["tool_interest"].items():
        if col in df.columns:
            adoption_vars[f"Tool adoption interest: {label}"] = col
    for label, col in adoption_cols["genai_proficiency"].items():
        if col in df.columns:
            adoption_vars[f"GenAI proficiency: {label}"] = col
    return adoption_vars


def add_multiselect_yes_no_columns(df, adoption_cols):
    df_out = df.copy()
    adoption_flag_vars = {}
    multiselect_groups = {
        "Training/policy support": adoption_cols["training_policy"],
        "Barrier": adoption_cols["barriers"],
        "Formal policy": adoption_cols["formal_policies"],
    }
    for group_name, col_map in multiselect_groups.items():
        for label, col in col_map.items():
            if col not in df_out.columns:
                continue
            new_col = f"derived_{clean_column_name(group_name)}_{clean_column_name(label)}"
            df_out[new_col] = df_out[col].apply(lambda x: "Yes" if pd.notna(x) and x != 0 else "No")
            adoption_flag_vars[f"{group_name}: {label}"] = new_col
    return df_out, adoption_flag_vars


# ============================================================
# File uploader and settings
# ============================================================

# Show the upload prompt only before a file is uploaded. Once a file is present,
# the upload section is removed so the dashboard starts with the client-facing tabs.
upload_placeholder = st.empty()

with upload_placeholder.container():
    with tab_profile:
        st.markdown("### Upload Campion survey export")
        uploaded_file = st.file_uploader(
            "Upload the Excel survey file",
            type=["xlsx", "xls"],
            help="Upload the raw Excel export. The dashboard will clean the two-header structure automatically."
        )

if uploaded_file is None:
    with tab_profile:
        st.info("Upload the Campion EdTech Adoption survey file to generate the dashboard.")
    st.stop()
else:
    upload_placeholder.empty()

with st.sidebar:
    st.header("Dashboard Controls")
    sheet_name = st.text_input(
        "Excel sheet",
        value="0",
        help="Use 0 for the first sheet, or type the exact sheet name."
    )
    missing_threshold = st.slider(
        "Exclude highly incomplete responses",
        min_value=0,
        max_value=100,
        value=80,
        step=5,
        help="Responses with more than this percentage of missing fields will be excluded."
    )
    show_admin_details = st.checkbox("Show technical diagnostics", value=False)

try:
    sheet_to_read = int(sheet_name)
except ValueError:
    sheet_to_read = sheet_name


data_clean, raw, dropped_cols = clean_two_header_excel(
    uploaded_file,
    sheet_name=sheet_to_read,
    missing_threshold=missing_threshold
)


# ============================================================
# Detect core profile columns
# ============================================================

role_col = find_first_existing_col(data_clean, [
    "which_of_the_following_best_describes_your_role_select_one_response",
    "which_of_the_following_best_describes_your_role",
    "role"
])
if role_col is None:
    role_col = find_best_column(data_clean, include_terms=["role"], exclude_terms=["email", "name"])

confidence_matches = find_column_by_keywords(data_clean, include_terms=["confidence"])
confidence_col = confidence_matches[0] if confidence_matches else None

school_sector_col = find_first_existing_col(data_clean, [
    "what_is_your_school_sectorselect_one_what_is_your_school_sectorselect_one"
])
school_type_col = find_first_existing_col(data_clean, [
    "what_is_your_school_sectorselect_one_what_is_your_school_sectorselect_one_1"
])
students_enrolled_col = find_first_existing_col(data_clean, [
    "approximately_how_many_students_are_enrolled_at_your_school_in_totalselect_one_response"
])
state_col = find_first_existing_col(data_clean, [
    "which_state_or_territory_is_your_school_located_inselect_one_response"
])

if school_sector_col is None:
    school_sector_col = find_best_column(data_clean, include_terms=["school", "sector"], exclude_terms=["type"])
if school_type_col is None:
    school_type_col = find_best_column(data_clean, include_terms=["school", "type"])
if students_enrolled_col is None:
    students_enrolled_col = find_best_column(data_clean, include_terms=["students", "enrolled"])
if state_col is None:
    state_col = find_best_column(data_clean, include_terms=["state", "territory"])

available_profile_vars = {
    "Role": role_col,
    "Confidence": confidence_col,
    "School Sector": school_sector_col,
    "School Type": school_type_col,
    "Students Enrolled": students_enrolled_col,
    "State or Territory": state_col,
}
available_profile_vars = {label: col for label, col in available_profile_vars.items() if col is not None}

adoption_cols_global = get_school_adoption_columns(data_clean)
data_for_interactions, adoption_flag_vars = add_multiselect_yes_no_columns(data_clean, adoption_cols_global)
available_adoption_vars = build_adoption_interaction_vars(data_for_interactions, adoption_cols_global)
available_adoption_vars.update(adoption_flag_vars)


# ============================================================
# Executive Overview
# ============================================================

with tab_profile:
    st.header("Executive Overview")
    st.markdown(
        """
        <p class="section-note">
        This page summarises the respondent and school profile behind the Campion EdTech Adoption survey.
        It provides context for interpreting current usage, satisfaction, readiness, and future adoption priorities.
        </p>
        """,
        unsafe_allow_html=True
    )

    q15_cols_for_summary = find_q15_columns(data_clean)
    q15_long_for_summary = make_q15_long(data_clean, q15_cols_for_summary) if q15_cols_for_summary else pd.DataFrame()
    avg_satisfaction = q15_long_for_summary["satisfaction_score"].mean() if not q15_long_for_summary.empty else None

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Survey responses analysed", f"{data_clean.shape[0]:,}")
    col2.metric("School profile fields", len([x for x in [school_sector_col, school_type_col, students_enrolled_col, state_col] if x]))
    col3.metric("Teaching journey stages", len(stage_tasks))
    col4.metric("Average satisfaction", f"{avg_satisfaction:.1f} / 10" if avg_satisfaction is not None else "Not available")

    st.markdown("---")

    profile_chart_type = st.selectbox(
        "Choose profile view",
        ["Bar - Percentage", "Bar - Count", "Pie"],
        index=0,
        key="profile_chart_type"
    )

    st.subheader("Respondent profile")
    profile_col1, profile_col2 = st.columns(2)
    with profile_col1:
        if role_col:
            fig = plot_categorical_variable(
                data_clean,
                role_col,
                title="Respondent Roles in the Campion EdTech Adoption Survey",
                x_title="Role",
                chart_type=profile_chart_type,
                horizontal=True
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not detect respondent role column.")
    with profile_col2:
        if confidence_col:
            fig = plot_categorical_variable(
                data_clean,
                confidence_col,
                title="Current EdTech Confidence Among Respondents",
                x_title="Confidence Level",
                chart_type=profile_chart_type,
                horizontal=False
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Could not detect confidence column.")

    st.subheader("School profile")
    school_col1, school_col2 = st.columns(2)
    with school_col1:
        if school_sector_col:
            st.plotly_chart(
                plot_categorical_variable(
                    data_clean,
                    school_sector_col,
                    title="School Sector Representation",
                    x_title="School Sector",
                    chart_type=profile_chart_type
                ),
                use_container_width=True
            )
        if students_enrolled_col:
            st.plotly_chart(
                plot_categorical_variable(
                    data_clean,
                    students_enrolled_col,
                    title="School Size by Student Enrolment",
                    x_title="Students Enrolled",
                    chart_type=profile_chart_type
                ),
                use_container_width=True
            )
    with school_col2:
        if school_type_col:
            st.plotly_chart(
                plot_categorical_variable(
                    data_clean,
                    school_type_col,
                    title="School Type Representation",
                    x_title="School Type",
                    chart_type=profile_chart_type
                ),
                use_container_width=True
            )
        if state_col:
            st.plotly_chart(
                plot_categorical_variable(
                    data_clean,
                    state_col,
                    title="State and Territory Representation",
                    x_title="State or Territory",
                    chart_type=profile_chart_type,
                    horizontal=True
                ),
                use_container_width=True
            )


# ============================================================
# Current EdTech Use
# ============================================================

with tab_tool_use:
    st.header("Current EdTech Use Across the Teaching Journey")
    st.write(
        "This section shows where schools are currently using different categories of educational technology "
        "across planning, preparation, teaching, assessment, feedback, monitoring, and wellbeing. Percentages "
        "are calculated within respondents who selected at least one tool-use option for that stage."
    )

    tool_chart_type = st.selectbox(
        "Choose view",
        ["Detailed task view", "Heatmap summary", "Grouped comparison"],
        index=0,
        key="tool_chart_type"
    )

    selected_stages = st.multiselect(
        "Select teaching journey stages",
        options=list(stage_tasks.keys()),
        default=list(stage_tasks.keys()),
        key="selected_stages_tool_page"
    )

    all_stage_summaries = {}
    all_missing = []

    for stage_name in selected_stages:
        summary, missing_df, n_answered = make_stage_summary(data_clean, stage_name, stage_tasks[stage_name])
        all_stage_summaries[stage_name] = summary
        if not missing_df.empty:
            all_missing.append(missing_df)
        if summary.empty:
            st.warning(f"No columns found for {stage_name}.")
            continue

        if stage_name == "Assessment":
            facet_wrap, height = 3, 1000
        elif stage_name in ["Planning", "Monitoring and Progress", "Wellbeing"]:
            facet_wrap, height = 3, 650
        else:
            facet_wrap, height = 2, 800

        st.subheader(stage_name)
        st.caption(f"{n_answered} respondents selected at least one option in this stage.")

        if tool_chart_type == "Detailed task view":
            fig = plot_stage_facets(summary, stage_name=stage_name, facet_wrap=facet_wrap, height=height)
        elif tool_chart_type == "Heatmap summary":
            fig = plot_stage_heatmap(summary, stage_name=stage_name)
        else:
            fig = plot_stage_grouped_bar(summary, stage_name=stage_name)
        st.plotly_chart(fig, use_container_width=True)

    if show_admin_details:
        non_empty_summaries = [df for df in all_stage_summaries.values() if not df.empty]
        if non_empty_summaries:
            combined_tool_use = pd.concat(non_empty_summaries, ignore_index=True)
            with st.expander("Admin: combined tool-use summary"):
                st.dataframe(combined_tool_use, use_container_width=True)
        if all_missing:
            with st.expander("Admin: missing expected matrix columns"):
                st.dataframe(pd.concat(all_missing, ignore_index=True), use_container_width=True)


# ============================================================
# Satisfaction & Value
# ============================================================

with tab_satisfaction:
    st.header("Satisfaction & Perceived Value")
    st.write(
        "This section summarises how satisfied respondents are with the use and application "
        "of different EdTech product categories across the teaching journey."
    )

    q15_cols = find_q15_columns(data_clean)
    if len(q15_cols) == 0:
        st.warning("Could not automatically find satisfaction columns.")
    else:
        q15_long = make_q15_long(data_clean, q15_cols)
        if q15_long.empty:
            st.warning("Satisfaction columns were found, but no numeric satisfaction scores were detected.")
        else:
            satisfaction_chart_type = st.selectbox(
                "Choose view",
                ["Average satisfaction", "Satisfaction distribution", "Score spread"],
                index=0,
                key="satisfaction_chart_type"
            )
            if satisfaction_chart_type == "Average satisfaction":
                fig_mean, q15_summary = plot_q15_mean(q15_long)
                st.plotly_chart(fig_mean, use_container_width=True)
                if show_admin_details:
                    with st.expander("Admin: satisfaction summary table"):
                        st.dataframe(q15_summary, use_container_width=True)
            elif satisfaction_chart_type == "Satisfaction distribution":
                fig_heatmap, q15_dist = plot_q15_heatmap(q15_long)
                st.plotly_chart(fig_heatmap, use_container_width=True)
                if show_admin_details:
                    with st.expander("Admin: satisfaction distribution table"):
                        st.dataframe(q15_dist, use_container_width=True)
            else:
                st.plotly_chart(plot_q15_box(q15_long), use_container_width=True)


# ============================================================
# Adoption Priorities
# ============================================================

with tab_adoption:
    st.header("Adoption Priorities & Readiness")
    st.write(
        "This section highlights where schools are looking to expand EdTech use, the product categories they are "
        "prioritising, the barriers they face, and their current readiness for responsible generative AI adoption."
    )

    adoption_cols = get_school_adoption_columns(data_clean)

    adoption_view = st.selectbox(
        "Choose adoption insight",
        [
            "Near-term expansion plans",
            "Priority teaching journey areas",
            "Priority product categories",
            "Planned training and policy support",
            "Key barriers to adoption",
            "Policy maturity",
            "Generative AI capability",
            "Expected change in GenAI use"
        ],
        key="adoption_view"
    )

    adoption_chart_type = st.selectbox(
        "Choose view",
        ["Bar chart", "Heatmap", "Stacked bar"],
        key="adoption_chart_type"
    )

    if adoption_view == "Near-term expansion plans":
        col = adoption_cols["expand_next_12_months"]
        if col is None or col not in data_clean.columns:
            st.warning("Could not find the expansion plans column.")
        else:
            fig = plot_categorical_variable(
                data_clean,
                col,
                title="Near-Term Plans to Develop or Expand EdTech Use",
                x_title="Response",
                chart_type="Bar - Percentage",
                horizontal=True
            )
            st.plotly_chart(fig, use_container_width=True)

    elif adoption_view == "Priority teaching journey areas":
        likert_df = make_likert_long(data_clean, adoption_cols["journey_interest"], value_order=interest_order)
        if likert_df.empty:
            st.warning("Could not create teaching journey priority chart.")
        else:
            fig = plot_likert_heatmap(likert_df, "Priority Areas for EdTech Expansion") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Priority Areas for EdTech Expansion")
            st.plotly_chart(fig, use_container_width=True)

    elif adoption_view == "Priority product categories":
        likert_df = make_likert_long(data_clean, adoption_cols["tool_interest"], value_order=interest_order)
        if likert_df.empty:
            st.warning("Could not create product category priority chart.")
        else:
            fig = plot_likert_heatmap(likert_df, "Priority EdTech Product Categories for Adoption or Expansion") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Priority EdTech Product Categories for Adoption or Expansion")
            st.plotly_chart(fig, use_container_width=True)

    elif adoption_view == "Planned training and policy support":
        summary = make_multiselect_summary(data_clean, adoption_cols["training_policy"])
        if summary.empty:
            st.warning("Could not create training and policy support chart.")
        else:
            st.plotly_chart(plot_multiselect_bar(summary, "Planned Training and Policy Support for Expansion"), use_container_width=True)

    elif adoption_view == "Key barriers to adoption":
        summary = make_multiselect_summary(data_clean, adoption_cols["barriers"])
        if summary.empty:
            st.warning("Could not create barriers chart.")
        else:
            st.plotly_chart(plot_multiselect_bar(summary, "Key Barriers to EdTech and Generative AI Adoption"), use_container_width=True)

    elif adoption_view == "Policy maturity":
        summary = make_multiselect_summary(data_clean, adoption_cols["formal_policies"])
        if summary.empty:
            st.warning("Could not create policy maturity chart.")
        else:
            st.plotly_chart(plot_multiselect_bar(summary, "Formal Policies Covering EdTech and AI"), use_container_width=True)

    elif adoption_view == "Generative AI capability":
        likert_df = make_likert_long(data_clean, adoption_cols["genai_proficiency"], value_order=proficiency_order)
        if likert_df.empty:
            st.warning("Could not create GenAI capability chart.")
        else:
            fig = plot_likert_heatmap(likert_df, "Current Generative AI Capability Across Key Areas") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Current Generative AI Capability Across Key Areas")
            st.plotly_chart(fig, use_container_width=True)

    elif adoption_view == "Expected change in GenAI use":
        col = adoption_cols["future_genai_use"]
        if col is None or col not in data_clean.columns:
            st.warning("Could not find the future GenAI use column.")
        else:
            fig = plot_categorical_variable(
                data_clean,
                col,
                title="Expected Change in Generative AI Use Over the Next 12 Months",
                x_title="Expected Change",
                chart_type="Bar - Percentage",
                horizontal=True
            )
            st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Strategic Segments
# ============================================================

with tab_interactions:
    st.header("Strategic Segments")
    st.write(
        "Use this section to identify how EdTech adoption, satisfaction, readiness, and barriers differ across "
        "school and respondent segments. These views are useful for identifying priority segments, support needs, "
        "and product opportunities."
    )

    if len(available_profile_vars) == 0 and len(available_adoption_vars) == 0:
        st.warning("Not enough variables were detected to create interaction charts.")
    else:
        interaction_type = st.selectbox(
            "Choose segmentation analysis",
            [
                "School/respondent profile comparison",
                "Profile by adoption readiness",
                "Adoption readiness comparison",
                "Profile by current EdTech use",
                "Adoption readiness by current EdTech use",
                "Profile by satisfaction",
                "Adoption readiness by satisfaction"
            ],
            key="interaction_type"
        )

        if interaction_type == "School/respondent profile comparison":
            if len(available_profile_vars) < 2:
                st.warning("At least two profile variables are needed for this interaction.")
            else:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    row_var_label = st.selectbox("Rows", list(available_profile_vars.keys()), index=0, key="row_var_label_profile_profile")
                with col_b:
                    col_var_label = st.selectbox("Columns", list(available_profile_vars.keys()), index=min(1, len(available_profile_vars) - 1), key="col_var_label_profile_profile")
                with col_c:
                    interaction_chart_type = st.selectbox("Choose view", ["Heatmap", "Grouped bar chart"], key="profile_profile_chart_type")
                fig = plot_crosstab_percent(
                    data_for_interactions,
                    row_col=available_profile_vars[row_var_label],
                    col_col=available_profile_vars[col_var_label],
                    row_label=row_var_label,
                    col_label=col_var_label,
                    title=f"{row_var_label} × {col_var_label}",
                    chart_type=interaction_chart_type
                )
                st.plotly_chart(fig, use_container_width=True)

        elif interaction_type == "Profile by adoption readiness":
            if len(available_profile_vars) == 0 or len(available_adoption_vars) == 0:
                st.warning("Profile or adoption/readiness variables were not detected.")
            else:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    row_var_label = st.selectbox("Profile variable", list(available_profile_vars.keys()), key="profile_adoption_row")
                with col_b:
                    col_var_label = st.selectbox("Adoption/readiness variable", list(available_adoption_vars.keys()), key="profile_adoption_col")
                with col_c:
                    interaction_chart_type = st.selectbox("Choose view", ["Heatmap", "Grouped bar chart"], key="profile_adoption_chart_type")
                fig = plot_crosstab_percent(
                    data_for_interactions,
                    row_col=available_profile_vars[row_var_label],
                    col_col=available_adoption_vars[col_var_label],
                    row_label=row_var_label,
                    col_label=col_var_label,
                    title=f"{row_var_label} × {col_var_label}",
                    chart_type=interaction_chart_type
                )
                st.plotly_chart(fig, use_container_width=True)

        elif interaction_type == "Adoption readiness comparison":
            if len(available_adoption_vars) < 2:
                st.warning("At least two adoption/readiness variables are needed for this interaction.")
            else:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    row_var_label = st.selectbox("Rows", list(available_adoption_vars.keys()), index=0, key="adoption_adoption_row")
                with col_b:
                    col_var_label = st.selectbox("Columns", list(available_adoption_vars.keys()), index=min(1, len(available_adoption_vars) - 1), key="adoption_adoption_col")
                with col_c:
                    interaction_chart_type = st.selectbox("Choose view", ["Heatmap", "Grouped bar chart"], key="adoption_adoption_chart_type")
                fig = plot_crosstab_percent(
                    data_for_interactions,
                    row_col=available_adoption_vars[row_var_label],
                    col_col=available_adoption_vars[col_var_label],
                    row_label=row_var_label,
                    col_label=col_var_label,
                    title=f"{row_var_label} × {col_var_label}",
                    chart_type=interaction_chart_type
                )
                st.plotly_chart(fig, use_container_width=True)

        elif interaction_type in ["Profile by current EdTech use", "Adoption readiness by current EdTech use"]:
            use_adoption = interaction_type == "Adoption readiness by current EdTech use"
            variable_source = available_adoption_vars if use_adoption else available_profile_vars
            if len(variable_source) == 0:
                st.warning("No grouping variables were detected.")
            else:
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    group_var_label = st.selectbox("Group current EdTech use by", list(variable_source.keys()), key=f"tool_group_{interaction_type}")
                with col_b:
                    selected_stage = st.selectbox("Teaching journey stage", list(stage_tasks.keys()), key=f"stage_{interaction_type}")
                with col_c:
                    tool_interaction_chart_type = st.selectbox("Choose view", ["Faceted grouped bar chart", "Heatmap"], key=f"tool_view_{interaction_type}")
                group_summary = make_stage_summary_by_group(
                    data_for_interactions,
                    stage_name=selected_stage,
                    tasks=stage_tasks[selected_stage],
                    group_col=variable_source[group_var_label]
                )
                if group_summary.empty:
                    st.warning("Could not create grouped tool-use summary for this selection.")
                else:
                    fig = plot_tool_use_by_group(
                        group_summary,
                        stage_name=selected_stage,
                        group_label=group_var_label,
                        chart_type=tool_interaction_chart_type
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    if show_admin_details:
                        with st.expander("Admin: grouped tool-use summary"):
                            st.dataframe(group_summary, use_container_width=True)

        elif interaction_type in ["Profile by satisfaction", "Adoption readiness by satisfaction"]:
            use_adoption = interaction_type == "Adoption readiness by satisfaction"
            variable_source = available_adoption_vars if use_adoption else available_profile_vars
            q15_cols = find_q15_columns(data_for_interactions)
            if len(q15_cols) == 0:
                st.warning("Could not automatically find satisfaction columns.")
            elif len(variable_source) == 0:
                st.warning("No grouping variables were detected.")
            else:
                group_var_label = st.selectbox("Group satisfaction by", list(variable_source.keys()), key=f"satisfaction_group_{interaction_type}")
                fig, sat_group_summary = plot_satisfaction_by_group(
                    data_for_interactions,
                    group_col=variable_source[group_var_label],
                    group_label=group_var_label,
                    q15_cols=q15_cols
                )
                if fig is None:
                    st.warning("Could not create satisfaction segmentation chart.")
                else:
                    st.plotly_chart(fig, use_container_width=True)
                    if show_admin_details:
                        with st.expander("Admin: satisfaction-by-group summary"):
                            st.dataframe(sat_group_summary, use_container_width=True)


# ============================================================
# Admin / Data Quality
# ============================================================

with tab_admin:
    st.header("Admin / Data Quality")
    st.write(
        "This section is intended for internal review. It shows cleaning decisions, detected columns, "
        "missing column diagnostics, and previews of the processed dataset."
    )

    st.subheader("Dataset summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Cleaned responses", data_clean.shape[0])
    col2.metric("Cleaned columns", data_clean.shape[1])
    col3.metric("PII/admin columns removed", len(dropped_cols))

    with st.expander("Dropped PII/admin columns"):
        st.write(dropped_cols)

    with st.expander("Detected profile columns"):
        st.dataframe(pd.DataFrame([{"field": key, "column": value} for key, value in available_profile_vars.items()]), use_container_width=True)

    with st.expander("Detected adoption/readiness variables"):
        st.dataframe(pd.DataFrame([{"label": label, "column": col} for label, col in available_adoption_vars.items()]), use_container_width=True)

    q15_cols = find_q15_columns(data_clean)
    with st.expander("Detected satisfaction columns"):
        st.dataframe(pd.DataFrame([{"tool_type": k, "column": v} for k, v in q15_cols.items()]), use_container_width=True)

    with st.expander("Preview cleaned data"):
        st.dataframe(data_clean.head(50), use_container_width=True)

    st.subheader("Download cleaned data")
    csv = data_clean.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download cleaned dataset as CSV",
        data=csv,
        file_name="campion_cleaned_edtech_adoption_data.csv",
        mime="text/csv"
    )
