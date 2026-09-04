# ZeroMind Knowledge Service

This directory owns the knowledge-base management backend.

The service will be implemented as an independently buildable Python application. It will
own its source code, tests, migrations, scripts, documentation, dependencies, container
definition, and database tables. Other applications will access it through HTTP rather than
reading or writing its tables directly.

Framework scaffolding and API design are intentionally deferred until the knowledge-service
requirements are defined.
