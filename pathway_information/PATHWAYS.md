# ADHD Pathway Models

## Overview

This document describes the pathway models used in the ADHD Discrete Event Simulation. The pathways are based on clinical frameworks and represent the progression of ADHD-related events, symptoms, and interventions over time.

## Reference Model

The simulation framework is informed by structured care pathways similar to the NHS Autism Pathway model structure:
- **Detection/Identification**: Initial recognition of symptoms
- **Assessment**: Comprehensive evaluation and diagnosis
- **Intervention**: Treatment and support pathways
- **Monitoring & Review**: Ongoing assessment and adjustments

## ADHD Pathway Components

### Events
Events represent discrete occurrences in the ADHD pathway:
- Symptom manifestation
- Clinical assessment
- Medication initiation
- Behavioral intervention
- Follow-up appointments
- Status changes

### States
Patient states during the pathway:
- Pre-diagnosis
- Assessment
- Diagnosed
- Under treatment
- In remission
- Relapse

### Transitions
Events trigger transitions between states based on clinical rules and probabilities.

## Defining Custom Pathways

Pathways can be customized by defining:
1. Initial state
2. Possible events and their triggers
3. State transitions
4. Time distributions for events
5. Probabilities and conditions

## Implementation

See the `src/pathways/` directory for pathway implementations and configurations.
