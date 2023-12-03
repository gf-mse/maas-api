from requests import request
import re
from requests_oauthlib import OAuth1Session

re_camelcase = re.compile(r"([A-Z]*[a-z0-9]+|[A-Z]+)(?:(?=[^a-z0-9])|\Z)")


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
        url = self.handler.uri.format(**kwargs)
        for p in self.handler.params:
            del kwargs[p]
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
            kw_params = kwargs.pop('params', {})
            params.update( kw_params )
        # POST requests
        elif self.method == 'POST':
            files = kwargs.get('files', {})
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

    def load_resources(self):
        response = self.session.get(f"{self.base_url}/api/2.0/describe/")
        self.description = response.json()
        for resource in self.description["resources"]:
            if resource["auth"]:
                name = handler_command_name(resource["name"])
                handler = Handler(name, self.session, resource["auth"])
                setattr(self, name, handler)
