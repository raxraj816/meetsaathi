# MeetSaathi v1 Architecture Decision Records

These decisions supersede disagreements in earlier Meeting, Learning, Interview and Conversation handoffs. Reviewed 18 October 2026. Revisit with measured data and changelog entry, not silent redesign.

| ADR | Decision | Rejected alternative | Rationale | Reverse if |
|---|---|---|---|---|
| ADR-001 | One app with contextual experience packs | Four separate apps | Shared user experience and reliable cross-context memory | Market/regulatory separation demands different releases |
| ADR-002 | Native Swift and Kotlin audio surfaces | Single JS-based audio layer | Reliable platform-specific capture, route and lifecycle control | Cross-platform abstraction proves equivalent on device matrix |
| ADR-003 | Four independent consent/control dimensions | All-in-one “companion enabled” toggle | Recording, proactive AI, private output and retention have different consequences | Never; required trust invariant |
| ADR-004 | Listener + text as initial defaults | Automatic Balanced and earbud voice | Socially safe predictable start | User deliberately chooses and persists eligible preference |
| ADR-005 | One prominent insight, not an endless feed | Continuous AI ticker | Reduce attention cost | Real user evidence shows benefit without distraction |
| ADR-006 | Provisional diarization + verified user correction | Automatically identify named humans | Nemotron is speaker activity, not identity verification | Proper consented identity mapping meets security/legal gates |
| ADR-007 | Source-linked claims with versioning | Mutable summaries treated as evidence | Supports truth, corrections, provenance and deletion | Never |
| ADR-008 | PostgreSQL+pgvector and durable jobs first | Neo4j/Kafka/K8s from day one | Production-grade transactions with lower initial operational overhead | Scale/graph workloads show measured bottlenecks |
| ADR-009 | On-device + cloud capability-aware hybrid | Either all-cloud or all-local globally | Device, model and legal limits differ | A measured single-mode deployment provides adequate coverage |
| ADR-010 | Separate stop and finalization lifecycle | End waits on cloud summary | User can stop microphone immediately even under outage | Never |
| ADR-011 | Mock interviews always accessible; live only with explicit authorization | Hidden coaching | Assessment integrity and legitimate adoption | Never |
| ADR-012 | Cross-session memory requires authorized space and selective retention | Always-save-everything | Privacy, trust and long-term quality | User explicitly selects additional retention |
| ADR-013 | Research preset in Learning | Fifth dedicated app tab | Keep home easy and evaluate real demand | Usage demonstrates distinct UX |
| ADR-014 | Voice output fails closed on private route loss | Auto-switch to phone loudspeaker | Prevent information leaking into room | Never |
| ADR-015 | Context packs configure intelligence, not copies of core infra | Four AI pipelines | Consistent quality, corrections, security and maintenance | Regulatory data isolation requires independent deploy |
