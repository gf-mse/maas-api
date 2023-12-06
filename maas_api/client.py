from requests import request
import re
from requests_oauthlib import OAuth1Session

# debug
import sys

# ( I believe this is borrowed from maascli/utils.py )
re_camelcase = re.compile(r"([A-Z]*[a-z0-9]+|[A-Z]+)(?:(?=[^a-z0-9])|\Z)")

# ------------------------------------------------------------------------

def handler_command_name(string):
    """Create a handler command name from an arbitrary string.
    Camel-case parts of string will be extracted, converted to lowercase,
    joined with hyphens, and the rest discarded. The term "handler" will also
    be removed if discovered amongst the aforementioned parts.
    """
    parts = re_camelcase.findall(string)
    parts = (part.lower() for part in parts)
    parts = (part for part in parts if part != "handler")
    return "_".join(parts)

def convert_files_arg( mapping ):
    """ [ https://stackoverflow.com/questions/10191733/how-to-do-a-http-delete-request-with-requests-library ]
        to form a multipart/form-data request, requests use the 'files' argument, which we shall prepare in a special way:
    """

    d = mapping
    result = {}
    for k, v in d.items():
        if not isinstance(v, (list, tuple)):
            result[k] = (None, str(v))
        else:
            result[k] = v
    return result


# ------------------------------------------------------------------------

class Action:
    def __init__(self, handler, name, method, op, doc, restful):
        self.handler = handler
        self.name = name
        self.method = method
        self.op = op
        self.doc = doc
        self.__doc__ = f"method: {method.lower()}\n---\n" + doc
        self.restful = restful

    def __call__(self, **kwargs):

        # // moving method default docstring into comments,
        # // so that we can use a dynamic docstring above )

        # // ex-docstring:
        ##  so far still supports old requests-style invocation format
        ##    (username='testuser1'),
        ##    (files = dict( username='testuser1', ...)),
        ##    (params(dict( name = 'node_timeout' ))
        ##  and a new unified call format
        ##    ( args=dict(...) )


        args = kwargs.get('args', kwargs.get('arguments', {}))
        for p in ('args', 'arguments'):
            if p in kwargs:
                del kwargs[p]

        url_args = kwargs.copy()
        url_args.update(args)
        url = self.handler.uri.format(**url_args)

        for p in self.handler.params:
            if p in kwargs:
                del kwargs[p]
            if p in args:
                del args[p]

        params = None
        if self.op is not None:
            params = {"op": self.op}
        # GET and DELETE requests
        # nb: code comments in "api.py" say that DELETE methods do not take parameters,
        #     [ https://github.com/cloudbase/maas/blob/master/src/maasserver/api.py ]
        #     but it is clearly not quite true -- for example,
        #     UserHandler::delete() has an optional 'transfer_resources_to' argument,
        #     which shall /probably/ come via the url part
        #     ( https://www.rfc-editor.org/rfc/rfc9110#DELETE )
        if self.method in ('GET', 'DELETE'):
            kw_params = kwargs.pop('params', args)
            if params:
                params.update( kw_params )
            else:
                params = kw_params
        # POST requests
        elif self.method == 'POST':
            files = kwargs.get('files', args)
            kwargs['files'] = convert_files_arg(files)

        response = self.handler.session.request(
            self.method, url, params=params, **kwargs
        )
        if response.ok:
            if self.method != 'DELETE':
                return response.json()
            else:
                return response.status_code
        raise Exception(response.text)


# ------------------------------------------------------------------------

class Handler:
    def __init__(self, name, session, definition):
        self.name = name
        self.session = session
        self.uri = definition["uri"]
        self.params = definition["params"]
        doc = definition.get("doc", None)
        self.__doc__ = f"path: {definition['path']!r}"
        if doc:
            self.__doc__ += f"\ndoc: {doc}"
        # self.actions = [Action(**action) for action in actions]
        for action in definition["actions"]:
            setattr(self, action["name"], Action(handler=self, **action))

# ------------------------------------------------------------------------

class Cache:
    """ so far - just an empty structure to keep things """
    pass


def _simple_key_iter( d, key ):
    """
        return the object or its elements if it is a sequence
    """

    if isinstance( d, dict ):
        obj = d.get(key)
        if isinstance(obj, (list, tuple)):
            for e in obj:
                yield e
        else:
            yield obj


def _key_spec_iter( d, attr_list ):
    """
        iterated over all "attr.spec" sub-attributes of a dictionary ;
        for every list entry, iterate over all elements
    """

    if attr_list:
        first = attr_list[0]
        rest = attr_list[1:]
        leaf = not rest

        for car in _simple_key_iter(d, first):
            if leaf:
                ## print( f"[iter-leaf]: {first} => {car}", file=sys.stderr)
                yield car
            else:
                if car:
                    for element in _key_spec_iter( car, rest ):
                        ## print( f"[iter-lvl]: {'.'.join(rest)} => {element}", file=sys.stderr)
                        yield element

##              if car:
##                  if leaf:
##                      yield car
##                  else:
##                      for element in _key_spec_iter( car, rest ):
##                          yield element


def _make_key_filter( dotted_spec, is_valid_fn ):
    """ 'attr.spec' => apply the filter ; list values are enumerated and treated as 'any' """

    attr_list = dotted_spec.split('.')
    def is_valid( d, attr_list = attr_list, passed_check = is_valid_fn):

        for value in _key_spec_iter( d, attr_list ):
            return passed_check(value)

    return is_valid


# ------------------------------------------------------------------------

class Client(object):
    """The MAAS client."""

    def __init__(self, url: str, api_key: str):
        """
        The constructor for the MAAS client.

        Parameters:
        url (string): base url for the MAAS server
        api_key (string): api key for the MAAS server
        """
        super(Client, self).__init__()
        consumer_key, key, secret = api_key.split(":")
        self.base_url = url.rstrip('/')
        self.session = OAuth1Session(
            consumer_key, resource_owner_key=key, resource_owner_secret=secret, signature_method = 'PLAINTEXT'
            ## consumer_key, resource_owner_key=key, resource_owner_secret=secret
        )
        self.load_resources()

        # // cached search
        self._cache = Cache()
        self._cache.machines = {} # system_id => data

    def load_resources(self):
        response = self.session.get(f"{self.base_url}/api/2.0/describe/")
        self.description = response.json()
        for resource in self.description["resources"]:
            if resource["auth"]:
                name = handler_command_name(resource["name"])
                handler = Handler(name, self.session, resource["auth"])
                setattr(self, name, handler)

    # --------------------------------------------------------------------
    # cached search

    def reload_cache(self, what = ['machines'], reset = False, **kwargs):
        """
            update the local system_id => <record> cache with results of a specific search
            ( an empty **kwards specification will load the whole set, which may take some memory )
        """

        if reset:
            self._cache.machines = {}

        machines = self._cache.machines

        machine_records = self.machines.read( arguments = kwargs )
        for m in machine_records:
            system_id = m.get('system_id')
            if system_id:
                machines[system_id] = m


    def find_machine_ids(self, filter_spec, update = False ):
        """
            filter the results by { 'key.spec' => 'prefix*' }
            or by  { 'key.spec' = lambda ... } ;
            filter specifications are AND-ed

            returns: a set of system_ids found
        """

        if update:
            self.reload_cache( what = ['machines'] )

        machines = self._cache.machines

        if filter_spec :

            results = {} # keyspec => machine ids

            for key_spec, filter_expr in filter_spec.items():

                found = set()

                # // make the predicate function

                # default is an identity test
                accept_fn = lambda x, v=filter_expr: ( x == v )

                if callable( filter_expr ):
                    accept_fn = filter_expr
                # rudimentary globbing
                if isinstance(filter_expr, str):
                    if filter_expr.startswith('*'):
                        s = filter_expr.lstrip('*')
                        accept_fn = lambda x, p=p: ( isinstance(x, str) and x.endswith(s) )
                    elif filter_expr.endswith('*'):
                        p = filter_expr.rstrip('*')
                        accept_fn = lambda x, p=p: ( isinstance(x, str) and x.startswith(p) )
                    else:
                        # keep the default identity test
                        pass
                elif isinstance(filter_expr, bool):
                    if filter_expr:
                        accept_fn = lambda x: (x)
                    else:
                        accept_fn = lambda x: (not x)

                # // apply the predicate function

                take_entry = _make_key_filter( key_spec, accept_fn )
                for system_id, machine_record in machines.items():
                    if take_entry(machine_record, ):
                        found.add( system_id )

                results[ key_spec ] = found

            # // apply the AND
            # take any
            result = results[set(results).pop()]
            # intersect
            for key_spec, subset in results.items():
                result = result & subset

        else:

            result = list(machines.keys())

        return result

    def find_machines_iter(self, filter_spec, update = False ):

        found_set = self.find_machine_ids(filter_spec = filter_spec, update = update)
        machines = self._cache.machines

        for sys_id in found_set:
            yield machines.get(sys_id)

    # tomahto, tomeito
    find_machine_iter = find_machines_iter

    def find_machines(self, filter_spec, update = False ):

        return list( self.find_machines_iter(filter_spec = filter_spec, update = update) )

