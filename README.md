# pg_schema_dump_parser
Generates nicely parsed schema files for PostgreSQL.

Every schema-qualified object is parsed into its own schema file while non-schema-qualified objects are parsed as utilities with
a generic schema name `others`.

## Requirements
- `python3.9` and above
- `pg_dump`
- `psql`

## Running the program
- Create `pg_schema_dump_parser.config` with template `pg_schema_dump_parser.config.sample` replacing the necessary values
- Then you can call the program as such:
  ```
  ./pg_schema_dump_parser.py --directory . --configfile pg_schema_dump_parser.config
  ```
  P.S In the above example, (`.`) translates to the current working directory.

## Metadata
A metadata is generated along with the schema files. It contains details of the database version, database host, database name, pg_dump version
and warnings.

# My Fork of [bolajiwahab / pg_schema_dump_parser]

## Why This Fork Exists
I forked this repository as I was unable to send these changes to the original developer.

## Changes in This Fork
-  To allow for processing of UNIQUE SEQUENCES
-  Added processing COLLATIONs.
-  Also added the ability to filter by what schema to export in the config.
   Can leave blank to process all schemas in the database.
- [Explain why these changes matter]

## How to Contribute
Feel free to submit PRs, report issues, or suggest improvements. Every contribution helps!

## Credits
This project builds on the fantastic work of [bolajiwahab / pg_schema_dump_parser].

