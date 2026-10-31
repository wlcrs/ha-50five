# Repository Instructions

## GraphQL Schema Is the Source of Truth

- Before changing a Pydantic response model, API query, or fixture representing a GraphQL response, inspect the corresponding operation and type definitions in `schema.graphql`.
- Follow the root query's return type through connection and nested object types. Do not infer the response type from a similarly named GraphQL type.
- Keep Pydantic fields aligned with the fields selected by the operation, their nesting, nullability, scalar types, and enum types. Use the exact GraphQL enum literals and casing.
- Do not remove schema-backed response fields from models or fixtures merely because current application code does not consume them. Do not add test fields that the operation does not select unless the test is specifically validating model handling of extra input.
- Prefer Pydantic validation of the raw GraphQL structure. Put derived convenience values in properties rather than flattening or normalizing the response into different model fields.
- Document each Pydantic model with its corresponding GraphQL type and, where useful, the operation/projection it represents. Mark integration aggregates as not being GraphQL types.
- When changing a query or response model, update representative fixtures and tests to match the SDL, then run the focused tests and the full test suite when practical.
