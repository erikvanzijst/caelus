## ADDED Requirements

### Requirement: A catalog value schema may declare var routing
A catalog file's `template.values_schema` MAY carry the routing markers defined in
`deployment-vars-schema-routing`: `x-caelus-target` and `x-caelus-sensitive` on a
top-level property, and `x-caelus-vars-additional` at the schema root.

The markers SHALL be optional, and a catalog file that carries none SHALL keep its
current meaning exactly: every property routes to the chart and the product accepts no
vars.

The catalog loader SHALL reject a file whose markers violate those rules, so that an
invalid declaration fails when the catalog is loaded rather than when a tenant later
deploys the product.

#### Scenario: A catalog file with no markers
- **WHEN** an existing catalog file is loaded unchanged
- **THEN** it is accepted
- **AND** the product accepts no vars

#### Scenario: A catalog file declaring a sensitive runtime property
- **WHEN** a catalog file marks a top-level string property as runtime and sensitive
- **THEN** it is accepted
- **AND** deployments of that product accept that var and never return its value

#### Scenario: A catalog file with an illegal marker
- **WHEN** a catalog file marks a nested property as runtime
- **THEN** loading the catalog fails with an error naming the file and the property
