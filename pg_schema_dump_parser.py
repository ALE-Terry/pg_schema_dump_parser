#!/usr/bin/env python3

# Run in bash:
# Make sure bash is set to the correct directory.
# $ python pg_schema_dump_parser.py --directory . --configfile pg_schema_dump.config
#

import os
import logging
import re
import argparse
import subprocess
import configparser
import shutil
from datetime import datetime, timezone
from time import time


APPLICATION_NAME = 'pg_schema_dump_parser'
warnings = False
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', encoding='utf-8', level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(APPLICATION_NAME)


def generate_metadata(directory: str, elapsed_time: str, warnings: bool) -> str:
    """ Generates metadata """

    host = config.get('postgresql', 'host')
    port = config.get('postgresql', 'port')
    dbname = config.get('postgresql', 'db')
    user = config.get('postgresql', 'user')
    password = config.get('postgresql', 'password')

    database_version = subprocess.Popen(
        ['psql',
        f"--dbname=postgresql://{user}:{password}@{host}:{port}/{dbname}?application_name={APPLICATION_NAME}",
         "-A",
         "--no-align",
         "--no-psqlrc",
         "--tuples-only",
         f"-c SELECT setting FROM pg_catalog.pg_settings WHERE name = 'server_version'"],
        stdout=subprocess.PIPE
    )  # pylint: disable=R1732

    pg_dump_version = subprocess.Popen(
        ['pg_dump',
         "--version",
         ],
        stdout=subprocess.PIPE
    )  # pylint: disable=R1732

    database_name = f"database_name: {dbname}"
    database_host = f"database_host: {host}"
    file_name = f"{directory}/schema/METADATA"
    database_version = f"database_version: {database_version.communicate()[0].decode('utf-8').strip()}"
    pg_dump_version = re.search(r"([0-9]*[.]?[0-9]+)", pg_dump_version.communicate()[0].decode('utf-8').strip()).group(1)
    pg_dump_version = f"pg_dump_version: {pg_dump_version}"

    if not os.path.exists(file_name):
        with open(file_name, 'a', encoding='utf-8') as file:
            file.write('# Do not edit\n' + f"# Generated by {APPLICATION_NAME} " + str(datetime.now(timezone.utc)) + f"\n# Schema parsing completed in {elapsed_time}\n\n")
            file.write(database_version + '\n')
            file.write(pg_dump_version + '\n')
            file.write(database_name + '\n')
            file.write(database_host + '\n')
            file.write(f"warnings: {warnings}" + '\n')


def read_in_chunk(stream: str, separator: str) -> str:
    """ Read in chunk https://stackoverflow.com/questions/47927039/reading-a-file-until-a-specific-character-in-python """
    buffer = ''
    while True:  # until EOF
        chunk = stream.readline(4096)  # 4096
        if not chunk:  # EOF?
            yield buffer
            break
        buffer += chunk
        while True:  # until no separator is found
            try:
                part, buffer = buffer.split(separator, 1)
            except ValueError:
                break
            else:
                yield part


def pg_schema_dump(host: str, dbname: str, schema: str, port: str, user: str, password: str) -> str:
    """ Get schema dump of a postgres database """

    parschema = '--schema'
    # added schema option to the parameters.
    # check if schema is blank for allowing all schemas in the database.
    if len(schema) == 0:
        parschema = ''
    # since schema can become empty, changed the list to
    # filter out blank entries to reduce potential errors.
    # added --no-owner option so the schema can be used on other databases easier.
    pg_dump_proc = subprocess.Popen(
        [
            x for x in
            [
                r'pg_dump.exe',
                f"--dbname=postgresql://{user}:{password}@{host}:{port}/{dbname}?application_name={APPLICATION_NAME}",
                "--schema-only",
                "--no-owner",
                f"{parschema}",
                f"{schema}"
                # '-f', dump_file,
            ]
            if x
        ],
        stdout=subprocess.PIPE
    )  # pylint: disable=R1732
    # clean up SET and SQL comments
    modified_dump = subprocess.Popen(['sed', '/^--/d;/^\\s*$/d;/^SET/d'], text=True, stdin=pg_dump_proc.stdout, stdout=subprocess.PIPE)  # pylint: disable=R1732
    return modified_dump.stdout


def parse_schema(directory: str, object_type: str, schema: str, object_name: str, definition: str, append: bool) -> None:
    """ Writes or appends to schema file """

    dir_path = f"{directory}/schema/{object_type}/{schema}"

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    file_name = f"{dir_path}/{object_name}.sql"

    if append:
        if not os.path.exists(file_name):
            with open(file_name, 'a', encoding='utf-8') as file:
                file.write(definition)
        else:
            with open(file_name, 'r+', encoding='utf-8') as file:
                current_content = [e+';\n' for e in read_in_chunk(file, ';\n') if e]
                line_found = any(definition in line for line in current_content)
                # if definition does not exist, append it to the schema file
                if not line_found:
                    file.seek(0, os.SEEK_END)
                    file.write(definition)
    else:
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write(definition)


def parse_object(stream: str, object_type: str, append: bool = True) -> None:
    """ Parses tables, views, materialized views, sequences, types, aggregates, defaults, constraints, rules,
    triggers, clustered indexes, comments, extensions, foreign tables, partitions """
    
    # changed 'CREATE SEQUENCE' to 'CREATE.*SEQUENCE' to allow for UNLOGGED SEQUENCE.
    # added 'CREATE COLLATION'
    schema_name = re.match(r"^(CREATE.*TABLE|COMMENT ON \w+|CREATE AGGREGATE|CREATE.*VIEW|CREATE TYPE|CREATE DOMAIN|CREATE COLLATION|CREATE.*SEQUENCE|ALTER.*TABLE \w+|ALTER.*TABLE|GRANT.*ON \w+|REVOKE.*ON \w+|.*TRIGGER.*?ON|.*RULE.*\n.*?ON.*) (\w+).(\w+)", stream, re.I).group(2)
    object_name = re.match(r"^(CREATE.*TABLE|COMMENT ON \w+|CREATE AGGREGATE|CREATE.*VIEW|CREATE TYPE|CREATE DOMAIN|CREATE COLLATION|CREATE.*SEQUENCE|ALTER.*TABLE \w+|ALTER.*TABLE|GRANT.*ON \w+|REVOKE.*ON \w+|.*TRIGGER.*?ON|.*RULE.*\n.*?ON.*) (\w+).(\w+)", stream, re.I).group(3)
    parse_schema(args.directory, object_type, schema_name, object_name, stream, append)


def parse_indexes(stream: str, object_type: str, append: bool = False) -> None:
    """ Parses indexes """
    index_name = re.match(r"^CREATE .*INDEX (\w+) ON (\w+).(\w+)", stream, re.I).group(1)
    schema_name = re.match(r"^CREATE .*INDEX (\w+) ON (\w+).(\w+)", stream, re.I).group(2)
    parse_schema(args.directory, object_type, schema_name, index_name, stream, append)


def parse_extensions(stream: str, object_type: str, append: bool = False) -> None:
    """ Parses extensions """
    extension_name = re.match(r"^CREATE EXTENSION.* (\w+) WITH SCHEMA (\w+)", stream, re.I).group(1)
    schema_name = re.match(r"^CREATE EXTENSION.* (\w+) WITH SCHEMA (\w+)", stream, re.I).group(2)
    parse_schema(args.directory, object_type, schema_name, extension_name, stream, append)


def parse_function(stream: str, object_type: str, append: bool = False) -> None:
    """ Parses function and procedure definition """

    # see https://www.geeksforgeeks.org/postgresql-dollar-quoted-string-constants/
    # because PG functions' bodies can be written as dollar quotes and single quotes
    # we rely solely on pg_get_functiondef for parsing functions

    host = config.get('postgresql', 'host')
    port = config.get('postgresql', 'port')
    dbname = config.get('postgresql', 'db')
    user = config.get('postgresql', 'user')
    password = config.get('postgresql', 'password')

    schema_name = re.match(r"^(CREATE FUNCTION|CREATE OR REPLACE FUNCTION|CREATE PROCEDURE|CREATE OR REPLACE PROCEDURE) (\w+).(\w+)", stream, re.I).group(2)
    func_name = re.match(r"^(CREATE FUNCTION|CREATE OR REPLACE FUNCTION|CREATE PROCEDURE|CREATE OR REPLACE PROCEDURE) (\w+).(\w+)", stream, re.I).group(3)

    with subprocess.Popen(
        ['psql',
         f"--dbname=postgresql://{user}:{password}@{host}:{port}/{dbname}?application_name={APPLICATION_NAME}",
         "-A",
         "--no-align",
         "--no-psqlrc",
         "--tuples-only",
         f"-c SELECT pg_catalog.string_agg(pg_catalog.pg_get_functiondef(f.oid), E';\n') || ';' AS def FROM (SELECT oid \
             FROM pg_catalog.pg_proc WHERE proname = '{func_name}' AND pronamespace = '{schema_name}'::regnamespace) AS f"],
        stdout=subprocess.PIPE
         ) as func_def_proc:

        func_def = func_def_proc.communicate()[0].decode('utf-8').strip()

        parse_schema(args.directory, object_type, schema_name, func_name, func_def + '\n', append)


def parse_utility(stream: str, utility_type: str, append: bool = True) -> None:
    """ Parses utilitities such as triggers, ownerships, acls, comments, mappings, schemas, rules, events, servers, collations """

    parse_schema(args.directory, 'utilities', 'others', utility_type, stream, append)


#  TODO: in a case a table depends on a user-defined function, we can simply add a dummy function before the create table


if __name__ == "__main__":
    file_path = os.path.abspath(__file__)
    args_parser = argparse.ArgumentParser(
        description="""Generates nicely parsed schema files""",
        epilog=f"example: {file_path} --directory . --configfile pg_schema_dump.config",
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    args_parser.add_argument('--directory', required=True, help="Directory to drop the schema files into")
    args_parser.add_argument('--configfile', required=True, help="Database configuration file, see sample")
    args = args_parser.parse_args()

    thisfolder = os.path.dirname(os.path.abspath(__file__))
    test_config_path = os.path.join(thisfolder, 'pg_schema_dump.config')
    config = configparser.ConfigParser()
    #config.read(args.configfile)
    config.read(test_config_path)

    postgres_host = config.get('postgresql', 'host')
    postgres_port = config.get('postgresql', 'port')
    postgres_db = config.get('postgresql', 'db')
    # added schema option to allow getting just a single schema from a database.
    postgres_schema = config.get('postgresql', 'schema')
    postgres_user = config.get('postgresql', 'user')
    postgres_password = config.get('postgresql', 'password')

    # clean up previous parse if it exists
    if os.path.exists(f"{args.directory}/schema"):
        shutil.rmtree(f"{args.directory}/schema")

    start_time = time()

	#
    #	Added postgres_schema to the function parameters.
    #
    
    with pg_schema_dump(postgres_host, postgres_db, postgres_schema, postgres_port, postgres_user, postgres_password) as f:
        logger.info(f"Started parser: {APPLICATION_NAME}")
        for segment in read_in_chunk(f, separator=';\n'):
            if segment:
                segment = segment + ';\n'

            if segment.startswith(("CREATE TABLE", "CREATE UNLOGGED TABLE", "CREATE FOREIGN TABLE")):
                parse_object(segment, 'tables')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and "ALTER COLUMN" in segment:
                parse_object(segment, 'columns_mod')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and "CLUSTER ON" in segment:
                parse_object(segment, 'clustered_indexes')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and "ADD CONSTRAINT" in segment:
                parse_object(segment, 'constraints')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and "SET DEFAULT" in segment:
                parse_object(segment, 'defaults')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and ("ATTACH PARTITION" in segment or "INHERIT" in segment):
                parse_object(segment, 'partitions')
            elif segment.startswith(("CREATE INDEX", "CREATE UNIQUE INDEX")):
                parse_indexes(segment, 'indexes')
            elif segment.startswith(("CREATE VIEW", "CREATE OR REPLACE VIEW", "CREATE MATERIALIZED VIEW")):
                parse_object(segment, 'views')
            elif segment.startswith("CREATE AGGREGATE"):
                parse_object(segment, 'aggregates')
            elif segment.startswith(("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")):
                parse_function(segment, 'functions')
            elif segment.startswith(("CREATE PROCEDURE", "CREATE OR REPLACE PROCEDURE")):
                parse_function(segment, 'procedures')
            elif segment.startswith("CREATE TYPE"):
                parse_object(segment, 'types')
            elif segment.startswith("CREATE DOMAIN"):
                parse_object(segment, 'domains')
            # added 'CREATE UNLOGGED SEQUENCE' option.
            elif segment.startswith(("CREATE SEQUENCE", "CREATE UNLOGGED SEQUENCE")):
                parse_object(segment, 'sequences')
            elif segment.startswith(("CREATE TRIGGER", "CREATE OR REPLACE TRIGGER", "CREATE CONSTRAINT TRIGGER", "CREATE OR REPLACE CONSTRAINT TRIGGER", "ALTER TRIGGER")) or "DISABLE TRIGGER" in segment or re.search(r"ENABLE.*TRIGGER", segment):
                parse_object(segment, 'triggers')
            elif segment.startswith(("CREATE RULE", "CREATE OR REPLACE RULE", "ALTER RULE")) or "DISABLE RULE" in segment or re.search(r"ENABLE.*RULE", segment):
                parse_object(segment, 'rules')
            elif segment.startswith("CREATE SCHEMA"):
                parse_utility(segment, 'schemas')
            elif ("OWNER TO" in segment or "OWNED BY" in segment):
                parse_utility(segment, 'ownerships')
            elif ("GRANT" in segment or "REVOKE" in segment) and re.search(r"\w+\.\w+", segment):
                parse_object(segment, 'acls')
            elif ("GRANT" in segment or "REVOKE" in segment) and not re.search(r"\w+\.\w+", segment):
                parse_utility(segment, 'acls')
            elif segment.startswith("CREATE EXTENSION"):
                parse_extensions(segment, 'extensions')
            elif segment.startswith("CREATE SERVER"):
                parse_utility(segment, 'servers')
            elif segment.startswith("COMMENT") and re.search(r"\w+\.\w+", segment):
                parse_object(segment, 'comments')
            elif segment.startswith("COMMENT") and not re.search(r"\w+\.\w+", segment):
                parse_utility(segment, 'comments')
            elif segment.startswith(("CREATE EVENT TRIGGER", "ALTER EVENT TRIGGER")):
                parse_utility(segment, 'events')
            elif segment.startswith("CREATE USER MAPPING"):
                parse_utility(segment, 'mappings')
            elif segment.startswith("CREATE PUBLICATION"):
                parse_utility(segment, 'publications')
            elif segment.startswith("ALTER PUBLICATION") and "OWNER TO" not in segment:
                parse_utility(segment, 'publications')
            elif segment.startswith("CREATE SUBSCRIPTION"):
                parse_utility(segment, 'subscriptions')
            elif segment.startswith("ALTER SUBSCRIPTION") and "OWNER TO" not in segment:
                parse_utility(segment, 'subscriptions')
            # added 'CREATE COLLATION' option.
            elif segment.startswith("CREATE COLLATION"):
                parse_utility(segment, 'collations')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and "ADD GENERATED ALWAYS AS IDENTITY" in segment:
                parse_object(segment, 'identities')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and re.search(r".*ROW LEVEL SECURITY", segment):
                parse_object(segment, 'row_level_securities')
            elif segment.startswith(("ALTER TABLE", "ALTER FOREIGN TABLE")) and re.search(r"REPLICA IDENTITY", segment):
                parse_object(segment, 'replica_identities')
            elif segment.startswith(("CREATE", "ALTER")):
                # if there are segments not parsed by us, we simply raise a warning to inform the caller of such
                # printing the segment
                # if you notice this, kindly create an issue on https://github.com/bolajiwahab/pg_schema_dump_parser with
                # the segment sample
                logger.warning("Parsing of %s not yet implemented, kindly create an issue on https://github.com/bolajiwahab/pg_schema_dump_parser", segment)
                warnings = True

    elapsed_time = f"{(time() - start_time):.2f} seconds"

    if warnings:
        generate_metadata(args.directory, elapsed_time, warnings)
        logger.info("Schema parsing completed with warnings in %s", elapsed_time)
    else:
        generate_metadata(args.directory, elapsed_time, warnings)
        logger.info("Schema parsing completed with no errors in %s", elapsed_time)
