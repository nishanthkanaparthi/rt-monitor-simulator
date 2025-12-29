# Real-Time Monitor Simulator

A deterministic, event-driven simulator for monitoring sensor faults and alarm behavior in a real-time system.

This project models how alarms are raised, cleared, and re-raised in response to sensor spikes and dropouts, using a strict state machine and fully reproducible scenarios.

---

## Features

- Deterministic tick-based simulation
- Explicit alarm state machine:
  - NOMINAL
  - PENDING_RAISE
  - ALARMED
  - PENDING_CLEAR
- Scenario-driven fault injection
- Fully test-driven design with pytest
- CLI interface for running simulations
- Metrics collection (alarm counts, timing)

---

## Project Structure


