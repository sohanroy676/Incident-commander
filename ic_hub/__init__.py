"""ic_hub: a local web hub over the Incident Commander pipeline (stdlib only, 127.0.0.1).

The hub imports `incident_commander` and `ic_plus`; neither imports the hub. It adds wiring
(worlds built from uploads, a web approver, a replay of the finished trace) and never a decision.
"""
