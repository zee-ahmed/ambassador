from typing import ClassVar, Dict, Generator, Sequence, Tuple, Union

from kat.harness import Node, Query, Runner
from abstract_tests import AmbassadorTest, ServiceType, MappingTest, MatchTest, OptionTest

ConfigGenType = Generator[Union[str, Tuple[Node, str]], None, None]
QueryGenType = Generator[Query, None, None]

# This is a boneheaded simple sketch of some test stuff (kind of ignoring ServiceType right now)
#
# I think that we'd want, from the below:
#
# Plain
# Plain.SimpleMapping
# Plain.SimpleMapping.HdrMatch1-pos
# Plain.SimpleMapping.HdrMatch1-pos.AddRequestHeaders
# Plain.SimpleMapping.HdrMatch1-pos.UseWebsocket
# Plain.SimpleMapping.HdrMatch1-pos.all
# Plain.SimpleMapping.HdrMatch1-neg
# Plain.SimpleMapping.HdrMatch2-pos
# Plain.SimpleMapping.HdrMatch2-pos.AddRequestHeaders
# Plain.SimpleMapping.HdrMatch2-pos.UseWebsocket
# Plain.SimpleMapping.HdrMatch2-pos.all
# Plain.SimpleMapping.HdrMatch2-neg
# Plain.CanaryMapping
# Plain.CanaryMapping.HdrMatch1-pos
# Plain.CanaryMapping.HdrMatch1-pos.AddRequestHeaders
# Plain.CanaryMapping.HdrMatch1-pos.UseWebsocket
# Plain.CanaryMapping.HdrMatch1-pos.all
# Plain.CanaryMapping.HdrMatch1-neg
# Plain.CanaryMapping.HdrMatch2-pos
# Plain.CanaryMapping.HdrMatch2-pos.AddRequestHeaders
# Plain.CanaryMapping.HdrMatch2-pos.UseWebsocket
# Plain.CanaryMapping.HdrMatch2-pos.all
# Plain.CanaryMapping.HdrMatch2-neg
# TLS
# TLS.SimpleMapping
# TLS.SimpleMapping.HdrMatch1-pos
# TLS.SimpleMapping.HdrMatch1-pos.AddRequestHeaders
# TLS.SimpleMapping.HdrMatch1-pos.UseWebsocket
# TLS.SimpleMapping.HdrMatch1-pos.all
# TLS.SimpleMapping.HdrMatch1-neg
# TLS.SimpleMapping.HdrMatch2-pos
# TLS.SimpleMapping.HdrMatch2-pos.AddRequestHeaders
# TLS.SimpleMapping.HdrMatch2-pos.UseWebsocket
# TLS.SimpleMapping.HdrMatch2-pos.all
# TLS.SimpleMapping.HdrMatch2-neg
# TLS.CanaryMapping
# TLS.CanaryMapping.HdrMatch1-pos
# TLS.CanaryMapping.HdrMatch1-pos.AddRequestHeaders
# TLS.CanaryMapping.HdrMatch1-pos.UseWebsocket
# TLS.CanaryMapping.HdrMatch1-pos.all
# TLS.CanaryMapping.HdrMatch1-neg
# TLS.CanaryMapping.HdrMatch2-pos
# TLS.CanaryMapping.HdrMatch2-pos.AddRequestHeaders
# TLS.CanaryMapping.HdrMatch2-pos.UseWebsocket
# TLS.CanaryMapping.HdrMatch2-pos.all
# TLS.CanaryMapping.HdrMatch2-neg


class Plain(AmbassadorTest):
    """
    Creates an Ambassador that will be using plaintext.

    Every AmbassadorTest subclass gets to include manifests (which will be
    added to the base Ambassador manifest?), configs (which act like any other
    configs), and query/check pairs, which will be run to check basic Ambassador
    functionality.
    """

    def manifests(self) -> str:
        pass

    def config(self) -> ConfigGenType:
        pass

    def query(self) -> QueryGenType:
        pass

    def check(self) -> None:
        """No return value -- just asserts here."""
        pass


class TLS(AmbassadorTest):
    """
    This Ambassador will be using TLS.
    """
    pass    # not gonna spell most of these out.


class SimpleMapping(MappingTest):
    """
    MappingTests define a Mapping within an existing AmbassadorTest. They're a bit odd in that
    they need a ServiceType as an argument, but they don't really live _under_ the ServiceType.
    MatchTests and OptionTests live under MappingTests.

    MappingTests are expected to yield a config for the mapping they're creating, queries to
    test it, and checks to make sure that the queries work.
    """

    def config(self):
        yield self.target, self.format("""
---
apiVersion: ambassador/v0
kind:  Mapping
name:  {self.name}
prefix: /{self.name}/
service: http://{self.target.path.k8s}
""")

    def queries(self):
        yield Query(self.parent.url(self.name + "/"))

    def check(self):
        assert self.results[0].backend.name == self.target.path.k8s


class CanaryMapping(MappingTest):
    """
    More complex: we need to set up a couple of different things and test routing between them.
    """

    # XXX This sketch doesn't show initialization -- how does the CanaryMapping get
    # self.canary?

    def config(self):
        yield self.target, self.format("""
---
apiVersion: ambassador/v0
kind:  Mapping
name:  {self.name}
prefix: /{self.name}/
service: http://{self.target.path.k8s}
""")
        yield self.canary, self.format("""
---
apiVersion: ambassador/v0
kind:  Mapping
name:  {self.name}-canary
prefix: /{self.name}/
service: http://{self.canary.path.k8s}
weight: {self.weight}
""")

    def queries(self):
        for i in range(100):
            yield Query(self.parent.url(self.name + "/"))

    def check(self):
        hist = {}
        for r in self.results:
            hist[ r.backend.name ] = hist.get(r.backend.name, 0) + 1
        canary = 100 * hist.get(self.canary.path.k8s, 0) / len(self.results)
        main = 100 * hist.get(self.target.path.k8s, 0) / len(self.results)
        assert abs(self.weight - canary) < 25, (self.weight, canary)



class HdrMatch1(MatchTest):
    """
    Must live under an AmbassadorTest. The base case here is that we'll yield
    a single Config, and then do some tests where we expect the match to succeed
    and some where we don't.

    Where we expect the match to succeed - the positive_queries - it makes sense to
    continue with OptionTests below us.

    Where we don' - the negative_queries - it doesn't make sense to continue with
    OptionTests below us.
    """
    debug: True


    def config(self):
        yield """
headers:
  x-demo-mode: host
"""

    def positive_queries(self, parent_url):
        yield Query(parent_url, headers={ 'x-demo-mode: host' })

    def negative_queries(self, parent_url):
        yield Query(parent_url, expected=404)


class HdrMatch2(MatchTest):
    """
    Just like HdrMatch1, except we're using a presence check instead of an exact header
    match.
    """
    debug: True

    def config(self):
        yield """
headers:
  x-demo-mode: true
"""

    def positive_queries(self, parent_url):
        yield Query(parent_url, headers={'x-demo-mode: host'})

    def negative_queries(self, parent_url):
        yield Query(parent_url, expected=404)


class AddRequestHeaders(OptionTest):
    """
    OptionTests modify a particular MappingTest with options that don't change what
    matches, but instead change how things behave.
    """

    VALUES: ClassVar[Sequence[Dict[str, str]]] = (
        { "foo": "bar" },
        { "moo": "arf" }
    )

    def config(self):
        yield "add_request_headers: %s" % json.dumps(self.value)

    def check(self):
        for r in self.parent.results:
            for k, v in self.value.items():
                actual = r.backend.request.headers.get(k.lower())
                assert actual == [v], (actual, [v])


class UseWebsocket(OptionTest):
    # TODO: add a check with a websocket client as soon as we have backend support for it

    def config(self):
        yield 'use_websocket: true'
