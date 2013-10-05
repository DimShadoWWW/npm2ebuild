#!/usr/bin/python

import json
import os
import sys
import shutil
import urllib
import zipfile
from distutils import version
import re
import functools

@functools.total_ordering
class NumberedVersion(version.Version):
    """
    A more flexible implementation of distutils.version.StrictVersion

    This implementation allows to specify:
    - an arbitrary number of version numbers:
        not only '1.2.3' , but also '1.2.3.4.5'
    - the separator between version numbers:
        '1-2-3' is allowed when '-' is specified as separator
    - an arbitrary ordering of pre-release tags:
        1.1alpha3 < 1.1beta2 < 1.1rc1 < 1.1
        when ["alpha", "beta", "rc"] is specified as pre-release tag list
    """

    def __init__(self, vstring=None, sep='.', prerel_tags=('a', 'b')):
        version.Version.__init__(self) 
            # super() is better here, but Version is an old-style class

        self.sep = sep
        self.prerel_tags = dict(zip(prerel_tags, xrange(len(prerel_tags))))
        self.version_re = self._compile_pattern(sep, self.prerel_tags.keys())
        self.sep_re = re.compile(re.escape(sep))

        if vstring:
            self.parse(vstring)


    _re_prerel_tag = 'rel_tag'
    _re_prerel_num = 'tag_num'

    def _compile_pattern(self, sep, prerel_tags):
        sep = re.escape(sep)
        tags = '|'.join(re.escape(tag) for tag in prerel_tags)

        if tags:
            release_re = '(?:(?P<{tn}>{tags})(?P<{nn}>\d*))?'\
                .format(tags=tags, tn=self._re_prerel_tag, nn=self._re_prerel_num)
        else:
            release_re = ''

        return re.compile(r'^(\d+)(?:{sep}(\d+))*{rel}$'\
            .format(sep=sep, rel=release_re))

    def parse(self, vstring):
        m = self.version_re.match(vstring)
        if not m:
            print self.version_re.pattern 
            raise ValueError("invalid version number '{}'".format(vstring))

        tag = m.group(self._re_prerel_tag)
        tag_num = m.group(self._re_prerel_num)

        try:
            if tag is not None and tag_num is not None:
                self.prerelease = (tag, int(tag_num))
                vnum_string = vstring[:-(len(tag) + len(tag_num))]
            else:
                self.prerelease = None
                vnum_string = vstring
        except:
            self.prerelease = None
            vnum_string = "0"

        self.version = tuple(map(int, self.sep_re.split(vnum_string)))


    def __repr__(self):
        return "{cls} ('{vstring}', '{sep}', {prerel_tags})"\
            .format(cls=self.__class__.__name__, vstring=str(self),
                sep=self.sep, prerel_tags = list(self.prerel_tags.keys()))

    def __str__(self):
        s = self.sep.join(map(str,self.version))
        if self.prerelease:
            return s + "{}{}".format(*self.prerelease)
        else:
            return s

    def __lt__(self, other):
        """
        Fails when  the separator is not the same or when the pre-release tags
        are not the same or do not respect the same order.
        """
        # TODO deal with trailing zeroes: e.g. "1.2.0" == "1.2"
        if self.prerel_tags != other.prerel_tags or self.sep != other.sep:
            raise ValueError("Unable to compare: instances have different"
                " structures")

        if self.version == other.version and self.prerelease is not None and\
                other.prerelease is not None:

            tag_index = self.prerel_tags[self.prerelease[0]]
            other_index = self.prerel_tags[other.prerelease[0]]
            if tag_index == other_index:
                return self.prerelease[1] < other.prerelease[1]

            return tag_index < other_index

        elif self.version == other.version:
            return self.prerelease is not None and other.prerelease is None

        return self.version < other.version

    def __eq__(self, other):
        tag_index = self.prerel_tags[self.prerelease[0]]
        other_index = other.prerel_tags[other.prerelease[0]]
        return self.prerel_tags == other.prerel_tags and self.sep == other.sep\
            and self.version == other.version and tag_index == other_index and\
                self.prerelease[1] == other.prerelease[1]

class NpmPkg(object):
    """Npm package"""
    def __init__(self, name, minversion = "0.0.1"):
        super(NpmPkg, self).__init__()
        self.name = name
        self.minversion = minversion
        self.downloadInfo()
        self.loadVersions()
        self.lastversiondeps=""
        print "%s-%s" % (self.name, self.lastversion)
        if u"dependencies" in self.pkgjson[u'versions'][self.lastversion].keys():
            for n in self.pkgjson[u'versions'][self.lastversion][u"dependencies"].keys():
                d = self.pkgjson[u'versions'][self.lastversion][u"dependencies"][n].replace("~", "").replace("=", "").replace(">", "").replace("<", "")
                self.checkDependencies(n, d)
                if d == "*":
                    self.lastversiondeps = "%s       dev-nodejs/%s\n" % (self.lastversiondeps, n)
                else:
                    self.lastversiondeps = "%s       >=dev-nodejs/%s-%s\n" % (self.lastversiondeps, n, d)
        self.makeEbuild()
        # for k in self.versions:
        #     for n in self.pkgjson[u'versions'][k][u"dependencies"].keys():
        #         print ">=dev-nodejs/%s-%s" % (n, self.pkgjson[u'versions'][k][u"dependencies"][n].replace("~", ""))
        #     print "-------"

    """Download registry information"""
    def downloadInfo(self):
        f = urllib.urlopen("http://registry.npmjs.org/%s" % self.name)
        # f.read()
        self.pkgjson = json.loads(f.read())

    """Make ebuild file"""
    def makeEbuild(self):
        if not os.path.exists(os.path.join("dev-nodejs",self.pkgjson[u'name'])):
            os.makedirs(os.path.join("dev-nodejs",self.pkgjson[u'name']))
        if not os.path.exists(os.path.join("dev-nodejs",self.pkgjson[u'name'], "%s-%s.ebuild" % (self.pkgjson[u'name'], self.lastversion))):
            version_adjust=''
            if re.sub("-[0-9]+$", '', self.lastversion) == self.lastversion:
                version_adjust="""
MY_PV="%s"
SRC_URI="http://registry.npmjs.org/${PN}/-/${PN}-${MY_PV}.tgz"
S="${WORKDIR}/${PN}-${MY_PV}"
                """ % (self.lastversion)
            print os.path.join("dev-nodejs",self.pkgjson[u'name'], "%s-%s.ebuild" % (self.pkgjson[u'name'], re.sub("-[0-9]+$", '', self.lastversion)))
            with open(os.path.join("dev-nodejs",self.pkgjson[u'name'], "%s-%s.ebuild" % (self.pkgjson[u'name'], re.sub("-[0-9]+$", '', self.lastversion))), "w") as f:
                f.write("""
# Copyright 1999-2013 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

EAPI=5

inherit npm

DESCRIPTION="%s"
%s

LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64 ~x86"
IUSE=""

DEPEND=""
RDEPEND=">=net-libs/nodejs-0.8.10
%s${DEPEND}"
""" % (
                        self.pkgjson[u'description'].replace("`", "'"),
                        version_adjust,
                        self.lastversiondeps
                        ))

    """Download file"""
    def downloadPkg(self):
        print "http://registry.npmjs.org/%s/-/%s.tgz" % (self.name, self.fullname)

    """Unpack downloaded file"""
    def unpackPkg(self):
        pass

    """Check package dependencies"""
    def checkDependencies(self, name, version):
        self.p = NpmPkg(name, version)

    """Load package versions"""
    def loadVersions(self):
        self.versions = self.pkgjson[u'versions'].keys()
        # vers = [tuple([int(x) for x in n.split(u'.')]) for n in self.versions]
        vers = sorted(self.versions, key=lambda v: NumberedVersion(v, '.', ['-rc', '-beta', '-alpha', '-']))
        # print vers
        self.lastversion =  vers[-1]
        # self.lastversion = ".".join([ str(i) for i in vers[-1]])

if len(sys.argv) > 1:
    p = NpmPkg(sys.argv[1])
else:
    print "Usage:\n\t%s <package name>" % sys.argv[0]

