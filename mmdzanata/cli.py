#!/usr/bin/python3
# -*- coding: utf-8 -*-
# This file is part of modulemd-zanata
# Copyright (C) 2017-2018 Stephen Gallagher
#
# Fedora-License-Identifier: MIT
# SPDX-2.0-License-Identifier: MIT
# SPDX-3.0-License-Identifier: MIT
#
# This program is free software.
# For more information on the license, see COPYING.
# For more information on free software, see
# <https://www.gnu.org/philosophy/free-sw.en.html>.

import click
import gi
import koji
import mmdzanata
import requests
import subprocess
import sys

from babel.messages import pofile

gi.require_version('Modulemd', '1.0')
from gi.repository import Modulemd

def get_fedora_rawhide_version(session, debug=False):
    # Koji sometimes disconnects for no apparent reason. Retry up to 5
    # times before failing.
    for attempt in range(5):
        try:
            build_targets = session.getBuildTargets('rawhide')
        except requests.exceptions.ConnectionError:
            if debug:
                print("Connection lost while retriving rawhide branch, "
                      "retrying...",
                      file=sys.stderr)
        else:
            # Succeeded this time, so break out of the loop
            break

    return build_targets[0][
        'build_tag_name'].partition('-build')[0]


def get_tags_for_fedora_branch(branch):
    return ['%s-modular' % branch,
            '%s-modular-override' % branch,
            '%s-modular-pending' % branch,
            '%s-modular-signing-pending' % branch,
            '%s-modular-updates' % branch,
            '%s-modular-updates-candidate' % branch,
            '%s-modular-updates-pending' % branch,
            '%s-modular-updates-testing' % branch,
            '%s-modular-updates-testing-pending' % branch]


##############################################################################
# Common options for all commands                                            #
##############################################################################


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.option('-k', '--koji-url',
              default='https://koji.fedoraproject.org/kojihub',
              type=str, help="""
The URL of the Koji build system.
(Default: https://koji.fedoraproject.org/kojihub)
""",
              metavar="<URL>")
@click.option('-b', '--branch', default="rawhide", type=str,
              help="The distribution release (Default: rawhide)",
              metavar="<branch_name>")
@click.option('-z', '--zanata-url',
              default="https://fedora.zanata.org",
              type=str, help="""
The Zanata URL
(Default: https://fedora.zanata.org/)
""",
              metavar="<zanata_project>")
@click.option('-p', '--zanata-project',
              default="fedora-modularity-translations",
              type=str, help="""
The Zanata project
(Default: fedora-modularity-translations)
""",
              metavar="<zanata_project>")
@click.option('-f', '--zanata-translation-document',
              default="fedora-modularity-translations",
              help="""
The name of the translated file in Zanata.
(Default: fedora-modularity-translations)
""",
              metavar="<translation_document>")
@click.pass_context
def cli(ctx, debug, branch, koji_url, zanata_url, zanata_project,
        zanata_translation_document):

    ctx.obj = dict()
    ctx.obj['debug'] = debug

    ctx.obj['session'] = koji.ClientSession(koji_url)

    ctx.obj['branch'] = branch

    if branch == "rawhide":
        ctx.obj['branch'] = get_fedora_rawhide_version(ctx.obj['session'])

    ctx.obj['zanata_url'] = zanata_url
    ctx.obj['zanata_project'] = zanata_project
    ctx.obj['zanata_translation_document'] = zanata_translation_document

##############################################################################
# Subcommands                                                                #
##############################################################################

##############################################################################
# `mmdzanata extract`                                                        #
##############################################################################

@cli.command()
@click.option('--upload/--no-upload', default=True,
               help='Whether to automatically push extracted strings to '
                    'Zanata')
@click.pass_context
def extract(ctx, upload):
    """
    Extract translations from all modules included in a particular version of
    Fedora or EPEL.
    """

    catalog = mmdzanata.get_module_catalog_from_tags(
        ctx.parent.obj['session'], get_tags_for_fedora_branch(
            ctx.parent.obj['branch']),
        debug=ctx.parent.obj['debug'])

    potfile = "%s.pot" % ctx.parent.obj['zanata_translation_document']

    with open(potfile, mode="wb") as f:
        pofile.write_po(f, catalog, sort_by_file=True)

    print ("Wrote extracted strings for %s to %s" % (ctx.obj['branch'],
                                                     potfile))

    # Optionally upload the extracted strings directly to Zanata
    if upload:
        # Use the zanata-cli to upload the pot file
        # It would be better to use the REST API directly here, but the XML
        # payload format is not documented.
        zanata_args = ['/usr/bin/zanata-cli', '-B', '-e', 'push',
                       '--url', ctx.parent.obj['zanata_url'],
                       '--project', ctx.parent.obj['zanata_project'],
                       '--project-type', 'gettext',
                       '--project-version', ctx.parent.obj['branch']]
        result = subprocess.run(zanata_args, capture_output=True)
        if result.returncode:
            print(result.stderr)
            print(result.stdout)
            sys.exit(1)


##############################################################################
# `mmdzanata generate_metadata`                                              #
##############################################################################

@cli.command()
@click.pass_context
def generate_metadata(ctx):
    """
    :return: 0 on successful creation of modulemd-translation,
    nonzero on failure.
    """

    zanata_rest_url = "%s/rest" % ctx.parent.obj['zanata_url']

    translations = mmdzanata.get_modulemd_translations(
        zanata_rest_url,
        ctx.parent.obj['zanata_project'],
        ctx.parent.obj['branch'],
        ctx.parent.obj['zanata_translation_document'],
        ctx.parent.obj['debug']
    )

    Modulemd.dump(sorted(translations), "%s.yaml" % (
        ctx.parent.obj['zanata_translation_document']))

    print("Wrote modulemd-translations YAML to %s.yaml" % (
        ctx.parent.obj['zanata_translation_document']))


if __name__ == "__main__":
    cli(obj={})