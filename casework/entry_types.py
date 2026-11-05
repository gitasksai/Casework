"""Definitions of the work-log tabs on a case.

Each entry type maps to a tab on the case page. `fields` drives both the add/edit
forms and validation: (column, label, widget, required, placeholder).
"""

ENTRY_TYPES = {
    "initial_response": {
        "label": "Initial Response",
        "singular": "initial response",
        "fields": [
            ("occurred_at", "Date / time sent", "datetime", True, ""),
            ("title", "Subject", "text", False, "e.g. Initial contact - acknowledging the issue"),
            ("body", "Initial response", "textarea", True, "What you sent / discussed in the first contact"),
        ],
    },
    "scoping": {
        "label": "Scoping Q&A",
        "singular": "scoping question",
        "fields": [
            ("occurred_at", "Asked on", "datetime", True, ""),
            ("question", "Scoping question", "textarea", True, "e.g. When did the issue start?"),
            ("response", "Customer response", "textarea", False, "Leave empty if still awaiting an answer"),
        ],
    },
    "troubleshooting": {
        "label": "Troubleshooting",
        "singular": "troubleshooting session",
        "fields": [
            ("occurred_at", "Session date / time", "datetime", True, ""),
            ("title", "Session title", "text", True, "e.g. Remote session - reviewed event logs"),
            ("duration_minutes", "Duration (minutes)", "number", False, "60"),
            ("body", "Actions taken / steps performed", "textarea", True, "Step-by-step what was done"),
            ("findings", "Findings / results", "textarea", False, "What you observed, errors, data collected"),
            ("next_steps", "Next steps", "textarea", False, "What follows from this session"),
        ],
    },
    "meeting": {
        "label": "Meeting Summaries",
        "singular": "meeting summary",
        "fields": [
            ("occurred_at", "Meeting date / time", "datetime", True, ""),
            ("title", "Meeting title", "text", True, "e.g. Status call with customer"),
            ("attendees", "Attendees", "text", False, "Names / roles"),
            ("body", "Meeting summary", "textarea", True, "Key discussion points and decisions"),
            ("action_items", "Action items", "textarea", False, "One per line, include owner"),
        ],
    },
    "note": {
        "label": "Other Notes",
        "singular": "note",
        "fields": [
            ("occurred_at", "Date / time", "datetime", True, ""),
            ("title", "Title", "text", True, ""),
            ("body", "Note", "textarea", True, "Anything else important for this case"),
        ],
    },
}

STANDARD_SCOPING_QUESTIONS = [
    "What is the exact problem / symptom, and what is the expected behaviour?",
    "When did the issue start, and has it ever worked correctly?",
    "What changed recently (patches, upgrades, configuration, network, infrastructure)?",
    "How many users / systems are affected, and is it all or a subset?",
    "Is the issue reproducible? What are the exact steps to reproduce?",
    "What error messages, codes or screenshots are available?",
    "What is the business impact, and is there a workaround in place?",
    "What logs / diagnostic data have already been collected?",
]
