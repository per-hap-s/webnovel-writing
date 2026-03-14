# Checker Output Schema

All review checkers must return one JSON object with these required keys:

```json
{
  "agent": "checker-name",
  "chapter": 100,
  "overall_score": 85,
  "pass": true,
  "issues": [],
  "metrics": {},
  "summary": "short summary"
}
```

## Required Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `agent` | string | yes | Checker identifier |
| `chapter` | integer | yes | Single chapter under review |
| `overall_score` | integer or number | yes | 0-100 |
| `pass` | boolean | yes | Checker pass/fail output |
| `issues` | array | yes | Flat list of issue objects |
| `metrics` | object | yes | Checker-specific metrics |
| `summary` | string | yes | Human-readable summary |

## Issue Shape

Each item in `issues` should follow this shape:

```json
{
  "id": "ISSUE_001",
  "type": "TIMELINE_ISSUE",
  "severity": "critical",
  "location": "scene 3",
  "description": "timeline conflict",
  "suggestion": "move the reveal to the next chapter",
  "can_override": false
}
```

`severity` must be one of `critical`, `high`, `medium`, or `low`.

## Review Gate Compatibility

The dashboard review gate consumes checker output directly.

Blocking rules:

- Any issue with `severity=critical` blocks the write workflow.
- Any issue with `type="TIMELINE_ISSUE"` and `severity in ["high", "critical"]` also blocks the write workflow.

Everything else may still be reported, but does not hard-block `polish`.
