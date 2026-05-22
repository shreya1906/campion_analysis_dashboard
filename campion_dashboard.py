import re
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

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


def wrap_label(value, width=32):
    """Insert line breaks into long category labels for more readable charts."""
    text = str(value)
    words = text.split()
    lines = []
    current = []
    current_len = 0
    for word in words:
        if current and current_len + len(word) + 1 > width:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + (1 if current_len else 0)
    if current:
        lines.append(" ".join(current))
    return "<br>".join(lines)


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


def order_categories_by_keywords(series, keyword_order):
    """
    Return observed categories in a preferred conceptual order, using keyword matching
    rather than exact text matching. This is safer for long SurveyMonkey labels.
    """
    observed = [str(x) for x in series.dropna().unique().tolist()]
    ordered = []

    for keyword_group in keyword_order:
        keyword_group_norm = [norm_text(k) for k in keyword_group]
        for category in observed:
            category_norm = norm_text(category)
            if category not in ordered and all(k in category_norm for k in keyword_group_norm):
                ordered.append(category)

    ordered += [category for category in observed if category not in ordered]
    return ordered


# ============================================================
# Generic plotting helpers
# ============================================================

def plot_categorical_variable(
    df,
    col,
    title,
    x_title,
    chart_type="Bar - Percentage",
    horizontal=False,
    category_order=None,
    sort_by_value=True,
    wrap_labels=False,
    label_width=34,
):
    summary = df[col].fillna("Missing").value_counts(sort=False).reset_index()
    summary.columns = ["category", "count"]
    summary["percent"] = summary["count"] / summary["count"].sum() * 100

    if category_order is not None:
        final_order = [str(cat) for cat in category_order if str(cat) in set(summary["category"].astype(str))]
        final_order += [cat for cat in summary["category"].astype(str).tolist() if cat not in final_order]
        summary["category"] = pd.Categorical(summary["category"].astype(str), categories=final_order, ordered=True)
        summary = summary.sort_values("category")
    elif sort_by_value:
        summary = summary.sort_values("percent", ascending=False)
    else:
        final_order = summary["category"].astype(str).tolist()

    summary["category_display"] = summary["category"].astype(str)
    if wrap_labels:
        summary["category_display"] = summary["category_display"].apply(lambda x: wrap_label(x, width=label_width))

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
        value_col = "count"
        value_label = "Number of Respondents"
        summary["bar_label"] = summary["count"].astype(str)
    else:
        value_col = "percent"
        value_label = "Percentage of Respondents"
        summary["bar_label"] = summary["percent"].round(1).astype(str) + "%"

    if horizontal:
        if category_order is None and sort_by_value:
            # For horizontal bars, ascending value order places the largest bars at the top visually.
            summary = summary.sort_values(value_col, ascending=True)

        fig = px.bar(
            summary,
            y="category_display",
            x=value_col,
            orientation="h",
            title=title,
            labels={"category_display": x_title, value_col: value_label},
            text="bar_label"
        )
        fig.update_traces(
            textposition="outside",
            customdata=summary[["category", "count", "percent"]],
            hovertemplate="<b>%{customdata[0]}</b><br>Count: %{customdata[1]}<br>Percentage: %{customdata[2]:.1f}%<extra></extra>"
        )
        fig.update_layout(
            template="plotly_white",
            height=max(480, 82 * len(summary)),
            xaxis_title=value_label,
            yaxis_title="",
            margin=dict(t=90, b=60, l=20, r=130),
            uniformtext_minsize=10,
            uniformtext_mode="hide"
        )
        if category_order is not None:
            display_order = [wrap_label(cat, label_width) if wrap_labels else cat for cat in final_order if cat in set(summary["category"].astype(str))]
            display_order += [x for x in summary["category_display"].astype(str).tolist() if x not in display_order]
            fig.update_yaxes(categoryorder="array", categoryarray=display_order[::-1])
    else:
        fig = px.bar(
            summary,
            x="category_display",
            y=value_col,
            title=title,
            labels={"category_display": x_title, value_col: value_label},
            text="bar_label"
        )
        fig.update_traces(
            textposition="outside",
            customdata=summary[["category", "count", "percent"]],
            hovertemplate="<b>%{customdata[0]}</b><br>Count: %{customdata[1]}<br>Percentage: %{customdata[2]:.1f}%<extra></extra>"
        )
        fig.update_layout(
            template="plotly_white",
            height=560,
            xaxis_tickangle=-25,
            xaxis_title=x_title,
            yaxis_title=value_label,
            margin=dict(t=90, b=140, l=70, r=40)
        )
        if category_order is not None:
            display_order = [wrap_label(cat, label_width) if wrap_labels else cat for cat in final_order if cat in set(summary["category"].astype(str))]
            display_order += [x for x in summary["category_display"].astype(str).tolist() if x not in display_order]
            fig.update_xaxes(categoryorder="array", categoryarray=display_order)

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
            "percent_stage_respondents": "Percentage of Respondents",
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
        legend_title="EdTech Product Type",
        margin=dict(t=110, b=170, l=80, r=40)
    )
    fig.update_xaxes(tickangle=90, title_text="")
    # Remove repeated y-axis titles from each facet. Repeated titles were overlapping
    # vertically when several facet rows were shown together.
    fig.update_yaxes(range=[0, max(10, y_max + 10)], title_text="")
    fig.add_annotation(
        text=f"Percentage of {stage_name} respondents",
        xref="paper",
        yref="paper",
        x=-0.055,
        y=0.5,
        showarrow=False,
        textangle=-90,
        font=dict(size=14, color="#4b5563")
    )
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


def make_tool_category_stage_summary(df, group_col=None):
    """
    Summarises each EdTech product category across all teaching journey stages.

    For each stage and tool category, the numerator is the number of respondents who
    selected that tool category for at least one task in that stage. The denominator is
    the number of respondents who selected at least one tool-use option in that stage.
    This makes it easier to see where each product category is most used across the
    teaching journey.
    """
    records = []

    if group_col is None:
        grouped_data = [("All respondents", df)]
    else:
        grouped_data = [
            ("Missing" if pd.isna(group_value) else str(group_value), group_df)
            for group_value, group_df in df.groupby(group_col, dropna=False)
        ]

    for group_label, group_df in grouped_data:
        for stage_name, tasks in stage_tasks.items():
            stage_matrix_cols = []
            tool_cols_by_tool = {}

            for task_label, task_stem in tasks.items():
                for tool_label, tool_key in tool_specs.items():
                    col = find_matrix_col(group_df, task_stem, tool_key)
                    if col is None:
                        continue
                    stage_matrix_cols.append(col)
                    tool_cols_by_tool.setdefault(tool_label, []).append(col)

            if len(stage_matrix_cols) == 0:
                continue

            answered_stage = (group_df[stage_matrix_cols].notna() & (group_df[stage_matrix_cols] != 0)).any(axis=1)
            n_stage = int(answered_stage.sum())

            for tool_label, tool_cols in tool_cols_by_tool.items():
                used_tool_in_stage = (group_df[tool_cols].notna() & (group_df[tool_cols] != 0)).any(axis=1)
                count = int((answered_stage & used_tool_in_stage).sum())
                percent = count / n_stage * 100 if n_stage > 0 else 0

                records.append({
                    "group_value": group_label,
                    "stage": stage_name,
                    "tool_type": tool_label,
                    "count": count,
                    "n_stage_respondents": n_stage,
                    "percent_stage_respondents": percent
                })

    return pd.DataFrame(records)


def plot_tool_category_across_stages(summary, selected_tool=None, chart_type="Line chart"):
    plot_df = summary.copy()
    stage_order = list(stage_tasks.keys())
    plot_df["stage"] = pd.Categorical(plot_df["stage"], categories=stage_order, ordered=True)
    plot_df = plot_df.sort_values(["tool_type", "stage"])

    if selected_tool is not None and selected_tool != "All categories":
        plot_df = plot_df[plot_df["tool_type"] == selected_tool].copy()

    if chart_type == "Heatmap":
        if selected_tool is not None and selected_tool != "All categories" and plot_df["group_value"].nunique() > 1:
            heatmap_data = plot_df.pivot(index="group_value", columns="stage", values="percent_stage_respondents").fillna(0)
            y_label = "Segment"
            title = f"{selected_tool}: Use Across Teaching Journey Stages by Segment"
        else:
            heatmap_data = plot_df.pivot(index="tool_type", columns="stage", values="percent_stage_respondents").fillna(0)
            y_label = "EdTech Product Category"
            title = "EdTech Product Category Use Across Teaching Journey Stages"

        fig = px.imshow(
            heatmap_data,
            text_auto=".1f",
            aspect="auto",
            title=title,
            labels={"x": "Teaching Journey Stage", "y": y_label, "color": "% of Stage Respondents"}
        )
        fig.update_layout(template="plotly_white", height=600, margin=dict(t=80, b=80, l=260, r=40))
        fig.update_xaxes(tickangle=-25)
        return fig

    if plot_df["group_value"].nunique() > 1 and selected_tool is not None and selected_tool != "All categories":
        fig = px.line(
            plot_df,
            x="stage",
            y="percent_stage_respondents",
            color="group_value",
            markers=True,
            title=f"{selected_tool}: Use Across Teaching Journey Stages by Segment",
            labels={"stage": "Teaching Journey Stage", "percent_stage_respondents": "% of Stage Respondents", "group_value": "Segment"},
            custom_data=["count", "n_stage_respondents"]
        )
    else:
        fig = px.line(
            plot_df,
            x="stage",
            y="percent_stage_respondents",
            color="tool_type",
            markers=True,
            title="EdTech Product Category Use Across Teaching Journey Stages",
            labels={"stage": "Teaching Journey Stage", "percent_stage_respondents": "% of Stage Respondents", "tool_type": "EdTech Product Category"},
            custom_data=["count", "n_stage_respondents"]
        )

    fig.update_traces(
        hovertemplate="<b>%{x}</b><br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<br>Stage respondents: %{customdata[1]}<extra></extra>"
    )
    fig.update_layout(template="plotly_white", height=650, xaxis_tickangle=-25, yaxis=dict(range=[0, 100]))
    return fig


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

# The section navigation is already visible at the top. The upload control is
# shown inside the Executive Overview tab only until a file is selected.
with tab_profile:
    upload_placeholder = st.empty()
    with upload_placeholder.container():
        st.markdown("### Upload Campion survey export")
        uploaded_file = st.file_uploader(
            "Upload the Excel survey file",
            type=["xlsx", "xls"],
            help="Upload the raw Excel export. The dashboard will clean the two-header structure automatically.",
            key="campion_survey_upload"
        )

if uploaded_file is None:
    with tab_profile:
        st.info("Upload the Campion EdTech Adoption survey file to generate the dashboard.")
    st.stop()

# Remove the uploader from view after upload, while keeping the uploaded file in memory
# for the current Streamlit rerun.
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
    "what_best_describes_your_primary_roleselect_the_most_senior_role_that_applies_to_you_response",
    "which_of_the_following_best_describes_your_role_select_one_response",
    "which_of_the_following_best_describes_your_role",
    "role"
])
if role_col is None:
    role_col = find_best_column(data_clean, include_terms=["role"], exclude_terms=["email", "name"])

confidence_col = find_first_existing_col(data_clean, [
    "how_would_you_describe_your_overall_confidence_in_using_educational_technology_in_your_teachingselect_one_response"
])
if confidence_col is None:
    confidence_col = find_best_column(
        data_clean,
        include_terms=["overall", "confidence", "educational", "technology"],
        exclude_terms=["barrier", "gap", "skills", "professional"]
    )
if confidence_col is None:
    confidence_matches = [
        col for col in find_column_by_keywords(data_clean, include_terms=["confidence"])
        if "barrier" not in col and "gap" not in col and "skills" not in col and "professional" not in col
    ]
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
    if role_col:
        fig = plot_categorical_variable(
            data_clean,
            role_col,
            title="Respondent Roles in the Campion EdTech Adoption Survey",
            x_title="Role",
            chart_type=profile_chart_type,
            horizontal=True,
            sort_by_value=False,
            wrap_labels=True,
            label_width=46
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Could not detect respondent role column.")

    if confidence_col:
        confidence_order = order_categories_by_keywords(
            data_clean[confidence_col],
            keyword_order=[
                ["lead", "champion"],
                ["very", "confident"],
                ["confident", "regularly"],
                ["somewhat", "comfortable"],
                ["not", "confident"],
            ]
        )
        fig = plot_categorical_variable(
            data_clean,
            confidence_col,
            title="Current EdTech Confidence Among Respondents",
            x_title="Confidence Level",
            chart_type=profile_chart_type,
            horizontal=True,
            category_order=confidence_order,
            sort_by_value=False,
            wrap_labels=True,
            label_width=46
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
                    chart_type=profile_chart_type,
                    sort_by_value=False
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
                    chart_type=profile_chart_type,
                    sort_by_value=False
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
                    chart_type=profile_chart_type,
                    sort_by_value=False
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
                    horizontal=True,
                    sort_by_value=False
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
        ["Detailed task view", "Stage heatmap"],
        index=0,
        key="tool_chart_type"
    )

    profile_split_options = {"No split": None}
    for label in ["School Sector", "School Type", "Students Enrolled", "State or Territory"]:
        if label in available_profile_vars:
            profile_split_options[label] = available_profile_vars[label]

    split_label = st.selectbox(
        "Split current EdTech use by",
        list(profile_split_options.keys()),
        index=0,
        key="current_use_split_label"
    )
    split_col = profile_split_options[split_label]

    all_stage_summaries = {}
    all_missing = []
    selected_stages = st.multiselect(
        "Select teaching journey stages",
        options=list(stage_tasks.keys()),
        default=list(stage_tasks.keys()),
        key="selected_stages_tool_page"
    )

    for stage_name in selected_stages:
        summary, missing_df, n_answered = make_stage_summary(data_clean, stage_name, stage_tasks[stage_name])
        all_stage_summaries[stage_name] = summary
        if not missing_df.empty:
            all_missing.append(missing_df)
        if summary.empty:
            st.warning(f"No columns found for {stage_name}.")
            continue

        if stage_name == "Assessment":
            facet_wrap, height = 3, 1050
        elif stage_name in ["Planning", "Monitoring and Progress", "Wellbeing"]:
            facet_wrap, height = 3, 700
        else:
            facet_wrap, height = 2, 900

        st.subheader(stage_name)
        st.caption(f"{n_answered} respondents selected at least one option in this stage.")

        if split_col is not None:
            group_summary = make_stage_summary_by_group(
                data_clean,
                stage_name=stage_name,
                tasks=stage_tasks[stage_name],
                group_col=split_col
            )
            if group_summary.empty:
                st.warning(f"Could not create split view for {stage_name} by {split_label}.")
                continue
            fig = plot_tool_use_by_group(
                group_summary,
                stage_name=stage_name,
                group_label=split_label,
                chart_type="Heatmap" if tool_chart_type == "Stage heatmap" else "Faceted grouped bar chart"
            )
        elif tool_chart_type == "Detailed task view":
            fig = plot_stage_facets(summary, stage_name=stage_name, facet_wrap=facet_wrap, height=height)
        else:
            fig = plot_stage_heatmap(summary, stage_name=stage_name)
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

    adoption_chart_type = st.selectbox(
        "Choose view for scaled-response insights",
        ["Bar chart", "Heatmap"],
        key="adoption_chart_type"
    )

    st.subheader("Near-term expansion plans")
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
            horizontal=True,
            sort_by_value=False,
            wrap_labels=True,
            label_width=44
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Priority teaching journey areas")
    likert_df = make_likert_long(data_clean, adoption_cols["journey_interest"], value_order=interest_order)
    if likert_df.empty:
        st.warning("Could not create teaching journey priority chart.")
    else:
        fig = plot_likert_heatmap(likert_df, "Priority Areas for EdTech Expansion") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Priority Areas for EdTech Expansion")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Priority product categories")
    likert_df = make_likert_long(data_clean, adoption_cols["tool_interest"], value_order=interest_order)
    if likert_df.empty:
        st.warning("Could not create product category priority chart.")
    else:
        fig = plot_likert_heatmap(likert_df, "Priority EdTech Product Categories for Adoption or Expansion") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Priority EdTech Product Categories for Adoption or Expansion")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Planned training and policy support")
    summary = make_multiselect_summary(data_clean, adoption_cols["training_policy"])
    if summary.empty:
        st.warning("Could not create training and policy support chart.")
    else:
        st.plotly_chart(plot_multiselect_bar(summary, "Planned Training and Policy Support for Expansion"), use_container_width=True)

    st.subheader("Key barriers to adoption")
    summary = make_multiselect_summary(data_clean, adoption_cols["barriers"])
    if summary.empty:
        st.warning("Could not create barriers chart.")
    else:
        st.plotly_chart(plot_multiselect_bar(summary, "Key Barriers to EdTech and Generative AI Adoption"), use_container_width=True)

    st.subheader("Policy maturity")
    summary = make_multiselect_summary(data_clean, adoption_cols["formal_policies"])
    if summary.empty:
        st.warning("Could not create policy maturity chart.")
    else:
        st.plotly_chart(plot_multiselect_bar(summary, "Formal Policies Covering EdTech and AI"), use_container_width=True)

    st.subheader("Generative AI capability")
    likert_df = make_likert_long(data_clean, adoption_cols["genai_proficiency"], value_order=proficiency_order)
    if likert_df.empty:
        st.warning("Could not create GenAI capability chart.")
    else:
        fig = plot_likert_heatmap(likert_df, "Current Generative AI Capability Across Key Areas") if adoption_chart_type == "Heatmap" else plot_likert_stacked_bar(likert_df, "Current Generative AI Capability Across Key Areas")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Expected change in GenAI use")
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
            horizontal=True,
            sort_by_value=False,
            wrap_labels=True,
            label_width=44
        )
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# Strategic Segments
# ============================================================

with tab_interactions:
    st.header("Strategic Segments")
    st.write(
        "Use this section to compare how EdTech use, satisfaction, adoption priorities, and readiness vary across "
        "school and respondent segments. The options are intentionally focused so the comparisons remain interpretable."
    )

    segment_data = data_for_interactions.copy()

    # ------------------------------------------------------------
    # Build demographic split options
    # ------------------------------------------------------------
    demographic_split_options = {"No split": None}
    for label, col in available_profile_vars.items():
        if col is not None and col in segment_data.columns:
            demographic_split_options[label] = col

    # ------------------------------------------------------------
    # Task-level usage profile, matching the client reference chart logic
    # ------------------------------------------------------------
    def make_task_level_tool_usage(df, split_col=None, min_group_n=1):
        """
        Create task-level usage percentages for each EdTech product category.

        This matches the reference graph logic:
        - For each teaching-journey task and product category, calculate the percentage
          of stage respondents who selected that product category for that task.
        - The box/range charts then summarise the spread of those task-level percentages.

        This is different from respondent-level usage intensity.
        """
        records = []

        if split_col is None:
            grouped_frames = [("All respondents", df)]
        else:
            grouped_frames = []
            for group_value, group_df in df.groupby(split_col, dropna=False):
                group_label = "Missing" if pd.isna(group_value) else str(group_value)
                if len(group_df) >= min_group_n:
                    grouped_frames.append((group_label, group_df))

        for segment_label, group_df in grouped_frames:
            for stage_name, tasks in stage_tasks.items():
                stage_summary, _, n_answered = make_stage_summary(group_df, stage_name, tasks)
                if stage_summary.empty:
                    continue

                temp = stage_summary.copy()
                temp["segment"] = segment_label
                temp["stage"] = stage_name
                temp["task_stage_label"] = temp["stage"] + ": " + temp["task"]
                temp["usage_percent"] = temp["percent_stage_respondents"]
                temp["segment_stage_respondents"] = n_answered
                records.append(temp[[
                    "segment",
                    "stage",
                    "task",
                    "task_stage_label",
                    "tool_type",
                    "usage_percent",
                    "count",
                    "segment_stage_respondents"
                ]])

        return pd.concat(records, ignore_index=True) if records else pd.DataFrame()

    def plot_task_usage_boxplot(task_usage_df, split_label, split_col=None):
        if split_col is None:
            fig = px.box(
                task_usage_df,
                x="usage_percent",
                y="tool_type",
                color="tool_type",
                points="all",
                orientation="h",
                title="Distribution of Task-Level EdTech Product Category Usage",
                labels={
                    "usage_percent": "Task-level usage (%)",
                    "tool_type": "EdTech Product Category"
                },
                color_discrete_map=color_map,
                custom_data=["task_stage_label", "count", "segment_stage_respondents"]
            )
            legend_title = "EdTech Product Category"
        else:
            fig = px.box(
                task_usage_df,
                x="usage_percent",
                y="tool_type",
                color="segment",
                points="all",
                orientation="h",
                title=f"Distribution of Task-Level EdTech Product Category Usage by {split_label}",
                labels={
                    "usage_percent": "Task-level usage (%)",
                    "tool_type": "EdTech Product Category",
                    "segment": split_label
                },
                custom_data=["task_stage_label", "count", "segment_stage_respondents"]
            )
            legend_title = split_label

        fig.update_traces(
            boxmean=False,
            jitter=0.35,
            pointpos=0,
            marker=dict(size=6, opacity=0.65),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Task: %{customdata[0]}<br>"
                "Usage: %{x:.1f}%<br>"
                "Respondents selecting this option: %{customdata[1]}<br>"
                "Stage respondents: %{customdata[2]}"
                "<extra></extra>"
            )
        )
        fig.update_layout(
            template="plotly_white",
            height=max(650, 135 * task_usage_df["tool_type"].nunique()),
            xaxis=dict(range=[-2, 102], ticksuffix="%"),
            margin=dict(t=90, b=80, l=280, r=40),
            legend_title=legend_title
        )
        return fig

    def plot_task_usage_range(task_usage_df, split_label, split_col=None, show_median=True):
        summary = task_usage_df.groupby(["tool_type", "segment"], as_index=False).agg(
            min_usage=("usage_percent", "min"),
            max_usage=("usage_percent", "max"),
            median_usage=("usage_percent", "median"),
            n_tasks=("usage_percent", "count")
        )
        summary["range_width"] = summary["max_usage"] - summary["min_usage"]
        summary["median_label"] = summary["median_usage"].round(1).astype(str) + "%"

        if split_col is None:
            fig = px.bar(
                summary,
                x="range_width",
                y="tool_type",
                base="min_usage",
                color="tool_type",
                orientation="h",
                title="Task-Level Usage Range by EdTech Product Category" if show_median else "Task-Level Usage Range by EdTech Product Category — Range Only",
                labels={
                    "range_width": "Task-level usage range (%)",
                    "tool_type": "EdTech Product Category"
                },
                color_discrete_map=color_map,
                custom_data=["min_usage", "max_usage", "median_usage", "n_tasks"]
            )
            fig.update_layout(showlegend=False)
        else:
            fig = px.bar(
                summary,
                x="range_width",
                y="tool_type",
                base="min_usage",
                color="segment",
                barmode="group",
                orientation="h",
                title=f"Task-Level Usage Range by EdTech Product Category and {split_label}" if show_median else f"Task-Level Usage Range by EdTech Product Category and {split_label} — Range Only",
                labels={
                    "range_width": "Task-level usage range (%)",
                    "tool_type": "EdTech Product Category",
                    "segment": split_label
                },
                custom_data=["min_usage", "max_usage", "median_usage", "n_tasks"]
            )

        fig.update_traces(
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Min task usage: %{customdata[0]:.1f}%<br>"
                "Max task usage: %{customdata[1]:.1f}%<br>"
                "Median task usage: %{customdata[2]:.1f}%<br>"
                "Tasks included: %{customdata[3]}"
                "<extra></extra>"
            )
        )

        if show_median:
            median_trace = go.Scatter(
                x=summary["median_usage"],
                y=summary["tool_type"],
                mode="markers+text",
                marker=dict(color="black", size=10, symbol="circle"),
                text=summary["median_label"],
                textposition="middle right",
                name="Median",
                customdata=summary[["segment", "n_tasks"]],
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Segment: %{customdata[0]}<br>"
                    "Median task usage: %{x:.1f}%<br>"
                    "Tasks included: %{customdata[1]}"
                    "<extra></extra>"
                )
            )
            fig.add_trace(median_trace)

        fig.update_layout(
            template="plotly_white",
            height=max(650, 135 * task_usage_df["tool_type"].nunique()),
            xaxis=dict(range=[0, 105], ticksuffix="%", title="Task-level usage (%)"),
            margin=dict(t=90, b=80, l=280, r=80),
            legend_title=split_label if split_col is not None else ("Summary" if show_median else "EdTech Product Category")
        )
        return fig

    # ------------------------------------------------------------
    # Build variable catalogue for other strategic comparisons
    # ------------------------------------------------------------
    variable_catalog = []

    def add_variable(label, column, section, var_type, role="Both"):
        if column is not None and column in segment_data.columns:
            variable_catalog.append({
                "label": label,
                "column": column,
                "section": section,
                "type": var_type,
                "role": role
            })

    for label, col in available_profile_vars.items():
        add_variable(label, col, "Sample characteristics", "categorical", role="Segment")

    for label, col in available_adoption_vars.items():
        add_variable(label, col, "Adoption priorities and readiness", "categorical", role="Both")

    q15_cols_for_segments = find_q15_columns(segment_data)
    satisfaction_score_cols = []
    for tool_type, col in q15_cols_for_segments.items():
        if col in segment_data.columns:
            score_col = f"derived_satisfaction_{clean_column_name(tool_type)}"
            segment_data[score_col] = segment_data[col].astype(str).str.extract(r"([0-9]+)").astype(float)
            segment_data.loc[~segment_data[score_col].between(1, 10), score_col] = pd.NA
            satisfaction_score_cols.append(score_col)
            add_variable(f"Satisfaction: {tool_type}", score_col, "Satisfaction and value", "numeric", role="Outcome")

    if satisfaction_score_cols:
        segment_data["derived_average_satisfaction_score"] = segment_data[satisfaction_score_cols].mean(axis=1)
        add_variable("Average satisfaction score", "derived_average_satisfaction_score", "Satisfaction and value", "numeric", role="Outcome")

    for stage_name, tasks in stage_tasks.items():
        stage_cols = []
        for task_label, task_stem in tasks.items():
            for tool_label, tool_key in tool_specs.items():
                col = find_matrix_col(segment_data, task_stem, tool_key)
                if col is not None:
                    stage_cols.append(col)
        if stage_cols:
            stage_any_col = f"derived_current_use_any_{clean_column_name(stage_name)}"
            stage_count_col = f"derived_current_use_count_{clean_column_name(stage_name)}"
            segment_data[stage_any_col] = (segment_data[stage_cols].notna() & (segment_data[stage_cols] != 0)).any(axis=1).map({True: "Yes", False: "No"})
            segment_data[stage_count_col] = (segment_data[stage_cols].notna() & (segment_data[stage_cols] != 0)).sum(axis=1)
            add_variable(f"Any current use in stage: {stage_name}", stage_any_col, "Current EdTech use", "categorical", role="Both")
            add_variable(f"Current use intensity: {stage_name}", stage_count_col, "Current EdTech use", "numeric", role="Outcome")

    variable_catalog_df = pd.DataFrame(variable_catalog).drop_duplicates(subset=["label", "column"])

    lens_options = [
        "EdTech category task-level usage",
        "School profile → current EdTech use",
        "School profile → satisfaction and value",
        "School profile → adoption priorities and readiness",
        "Current EdTech use → satisfaction and value",
        "Adoption readiness → current use or satisfaction"
    ]

    selected_lens = st.selectbox(
        "Strategic question",
        lens_options,
        key="strategic_lens"
    )

    if selected_lens == "EdTech category task-level usage":
        st.caption(
            "This view matches the reference chart logic. For each teaching task, it calculates the percentage of "
            "stage respondents who selected each EdTech product category. The box plot or range chart then summarises "
            "the spread of those task-level percentages. Dots represent tasks, not individual respondents."
        )

        split_col_1, split_col_2, split_col_3, split_col_4 = st.columns([1, 1, 1, 0.8])
        with split_col_1:
            split_label = st.selectbox(
                "Split chart by",
                list(demographic_split_options.keys()),
                index=0,
                key="task_usage_split"
            )
        with split_col_2:
            chart_view = st.selectbox(
                "Chart view",
                ["Box plot", "Range with median", "Range only"],
                index=0,
                key="task_usage_chart_view"
            )
        with split_col_3:
            selected_tools = st.multiselect(
                "EdTech product categories",
                list(tool_specs.keys()),
                default=list(tool_specs.keys()),
                key="task_usage_tools"
            )
        with split_col_4:
            min_group_n = st.slider(
                "Minimum group size",
                min_value=1,
                max_value=15,
                value=3,
                step=1,
                key="task_usage_min_group"
            )

        split_col = demographic_split_options[split_label]
        task_usage = make_task_level_tool_usage(segment_data, split_col=split_col, min_group_n=min_group_n)

        if selected_tools:
            task_usage = task_usage[task_usage["tool_type"].isin(selected_tools)].copy()

        if task_usage.empty:
            st.warning("No task-level usage data was available for the current selection.")
        else:
            if chart_view == "Range with median":
                fig = plot_task_usage_range(task_usage, split_label, split_col=split_col, show_median=True)
            elif chart_view == "Range only":
                fig = plot_task_usage_range(task_usage, split_label, split_col=split_col, show_median=False)
            else:
                fig = plot_task_usage_boxplot(task_usage, split_label, split_col=split_col)
            st.plotly_chart(fig, use_container_width=True)

            st.caption(
                "Reading guide: each dot represents one teaching task. The value is the percentage of stage respondents "
                "who selected that product category for that task. The box/range summarises variation across tasks."
            )

            if show_admin_details:
                with st.expander("Admin: task-level usage data"):
                    st.dataframe(task_usage, use_container_width=True)

    else:
        if variable_catalog_df.empty:
            st.warning("Not enough variables were detected to create strategic segment charts.")
        else:
            lens_map = {
                "School profile → current EdTech use": {
                    "segment_sections": ["Sample characteristics"],
                    "outcome_sections": ["Current EdTech use"],
                    "default_chart": "Mean / percentage bar"
                },
                "School profile → satisfaction and value": {
                    "segment_sections": ["Sample characteristics"],
                    "outcome_sections": ["Satisfaction and value"],
                    "default_chart": "Mean / percentage bar"
                },
                "School profile → adoption priorities and readiness": {
                    "segment_sections": ["Sample characteristics"],
                    "outcome_sections": ["Adoption priorities and readiness"],
                    "default_chart": "Heatmap"
                },
                "Current EdTech use → satisfaction and value": {
                    "segment_sections": ["Current EdTech use"],
                    "outcome_sections": ["Satisfaction and value"],
                    "default_chart": "Mean / percentage bar"
                },
                "Adoption readiness → current use or satisfaction": {
                    "segment_sections": ["Adoption priorities and readiness"],
                    "outcome_sections": ["Current EdTech use", "Satisfaction and value"],
                    "default_chart": "Heatmap"
                }
            }
            lens = lens_map[selected_lens]

            segment_vars = variable_catalog_df[
                (variable_catalog_df["type"] == "categorical")
                & (variable_catalog_df["section"].isin(lens["segment_sections"]))
            ].copy()
            outcome_vars = variable_catalog_df[
                (variable_catalog_df["role"].isin(["Outcome", "Both"]))
                & (variable_catalog_df["section"].isin(lens["outcome_sections"]))
            ].copy()

            if segment_vars.empty or outcome_vars.empty:
                st.warning("This strategic question does not have enough detected variables in the uploaded file.")
            else:
                controls_1, controls_2, controls_3 = st.columns([1, 1, 0.8])
                with controls_1:
                    segment_label = st.selectbox(
                        "Compare groups by",
                        segment_vars["label"].tolist(),
                        key="strategic_segment_by"
                    )
                with controls_2:
                    outcome_label = st.selectbox(
                        "Measure",
                        outcome_vars["label"].tolist(),
                        key="strategic_outcome"
                    )

                segment_row = segment_vars[segment_vars["label"] == segment_label].iloc[0]
                outcome_row = outcome_vars[outcome_vars["label"] == outcome_label].iloc[0]
                segment_col = segment_row["column"]
                outcome_col = outcome_row["column"]
                outcome_type = outcome_row["type"]

                if outcome_type == "numeric":
                    chart_options = ["Mean / percentage bar", "Distribution spread"]
                else:
                    chart_options = ["Heatmap", "Grouped bar"]

                with controls_3:
                    default_index = chart_options.index(lens["default_chart"]) if lens["default_chart"] in chart_options else 0
                    chart_choice = st.selectbox(
                        "Chart type",
                        chart_options,
                        index=default_index,
                        key="strategic_chart_type"
                    )

                min_group_n = st.slider(
                    "Minimum responses per displayed group",
                    min_value=1,
                    max_value=15,
                    value=3,
                    step=1,
                    help="Small groups are hidden to avoid unstable or misleading comparisons.",
                    key="strategic_general_min_group"
                )

                if segment_col == outcome_col:
                    st.warning("Please choose different variables for the group comparison and the measure.")
                else:
                    plot_df = segment_data[[segment_col, outcome_col]].copy()
                    plot_df[segment_col] = plot_df[segment_col].fillna("Missing")

                    group_sizes = plot_df.groupby(segment_col).size().reset_index(name="group_n")
                    valid_groups = group_sizes.loc[group_sizes["group_n"] >= min_group_n, segment_col].tolist()
                    plot_df = plot_df[plot_df[segment_col].isin(valid_groups)].copy()

                    if plot_df.empty:
                        st.warning("No groups met the minimum response threshold for this comparison.")
                    elif outcome_type == "numeric":
                        plot_df[outcome_col] = pd.to_numeric(plot_df[outcome_col], errors="coerce")
                        plot_df = plot_df.dropna(subset=[outcome_col])

                        if plot_df.empty:
                            st.warning("No valid numeric data was available for this selection.")
                        elif chart_choice == "Distribution spread":
                            fig = px.box(
                                plot_df,
                                x=segment_col,
                                y=outcome_col,
                                points="all",
                                title=f"{outcome_label} by {segment_label}",
                                labels={segment_col: segment_label, outcome_col: outcome_label}
                            )
                            fig.update_layout(template="plotly_white", height=650, xaxis_tickangle=-25, margin=dict(t=90, b=120, l=80, r=40))
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            summary = plot_df.groupby(segment_col, as_index=False).agg(
                                mean_value=(outcome_col, "mean"),
                                median_value=(outcome_col, "median"),
                                n=(outcome_col, "count")
                            )
                            summary = summary.sort_values("mean_value", ascending=False)
                            summary["label"] = summary["mean_value"].round(1).astype(str)
                            fig = px.bar(
                                summary,
                                x=segment_col,
                                y="mean_value",
                                title=f"{outcome_label} by {segment_label}",
                                labels={segment_col: segment_label, "mean_value": f"Average {outcome_label}"},
                                text="label",
                                custom_data=["median_value", "n"]
                            )
                            fig.update_traces(
                                textposition="outside",
                                hovertemplate="<b>%{x}</b><br>Mean: %{y:.2f}<br>Median: %{customdata[0]:.2f}<br>Responses: %{customdata[1]}<extra></extra>"
                            )
                            fig.update_layout(template="plotly_white", height=650, xaxis_tickangle=-25, margin=dict(t=90, b=120, l=80, r=40))
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        plot_df[outcome_col] = plot_df[outcome_col].fillna("Missing")

                        if chart_choice == "Grouped bar":
                            ctab = pd.crosstab(plot_df[segment_col], plot_df[outcome_col], normalize="index") * 100
                            count_tab = pd.crosstab(plot_df[segment_col], plot_df[outcome_col])
                            long_df = ctab.reset_index().melt(id_vars=segment_col, var_name=outcome_label, value_name="percent")
                            count_long = count_tab.reset_index().melt(id_vars=segment_col, var_name=outcome_label, value_name="count")
                            long_df = long_df.merge(count_long, on=[segment_col, outcome_label], how="left")

                            fig = px.bar(
                                long_df,
                                x=segment_col,
                                y="percent",
                                color=outcome_label,
                                barmode="group",
                                title=f"{outcome_label} by {segment_label}",
                                labels={segment_col: segment_label, "percent": "% within group", outcome_label: outcome_label},
                                custom_data=["count"]
                            )
                            fig.update_traces(
                                hovertemplate="<b>%{x}</b><br>Category: %{fullData.name}<br>Percentage: %{y:.1f}%<br>Count: %{customdata[0]}<extra></extra>"
                            )
                            fig.update_layout(template="plotly_white", height=650, xaxis_tickangle=-25, margin=dict(t=90, b=120, l=80, r=40))
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            fig = plot_crosstab_percent(
                                plot_df,
                                row_col=segment_col,
                                col_col=outcome_col,
                                row_label=segment_label,
                                col_label=outcome_label,
                                title=f"{outcome_label} by {segment_label}",
                                chart_type="Heatmap"
                            )
                            st.plotly_chart(fig, use_container_width=True)

                    if show_admin_details:
                        with st.expander("Admin: strategic segment source data"):
                            st.dataframe(plot_df, use_container_width=True)

    if show_admin_details:
        with st.expander("Admin: variables available in Strategic Segments"):
            st.dataframe(variable_catalog_df, use_container_width=True)


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
