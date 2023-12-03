
# Table of Contents

1.  [Quickstart](#orgc1e985f)
    1.  [Installing](#org8a0e592)
    2.  [Using](#org155b2b6)
2.  [Why?](#org5d3a245)
3.  [How?](#orgfb84d69)



<a id="orgc1e985f"></a>

# Quickstart

 * forked from Jelle Helsen's [maas-api](https://github.com/jellehelsen/maas-api), which is now archived and read-only.
 * README file below is modified, the original README is here: [(original README)](README.orig.md)

<a id="org8a0e592"></a>

## Installing

You can install [directly from a git repository](https://pip.pypa.io/en/stable/topics/vcs-support/) using pip:

    pip3 install git+https://github.com/gf-mse/maas-api.git

It depends on [requests-oauthlib](https://github.com/requests/requests-oauthlib), which provides OAuth 1.0a functionality and a common `requests` interface.

<a id="org155b2b6"></a>

## Using

You can use the api client the same way you would use the CLI. Assuming that MaaS is available at `http://192.0.2.10:5240` :

    from maas_api import Client
    
    client = Client("http://192.0.2.10:5240/MAAS", api_key="your:api:key")
    
    # check the object
    print( client.users.whoami.doc )

    # test connection
    import json
    print( json.dumps( client.users.read(), indent = 2 ) )
    # or
    print( client.users.whoami() )

    # allocate a machine
    machine = client.machines.allocate()
    # start deploy
    client.machine.deploy(system_id=machine["system_id"])
    # release the machine
    client.machine.release(system_id=machine["system_id"])


### Troubleshooting

    sudo tcpdump -A -i ${interface} 'host 192.0.2.10 and port 5240'


<a id="org5d3a245"></a>

# Why?

The official MAAS api client library [python-libmaas](https://pypi.org/project/python-libmaas/) did not receive any new
functionality that is available with MAAS.
There is however a [CLI](https://github.com/maas/maas/tree/master/src) written in python. This allows all the functionality to
be used.

To add, Jelle Helsen's code is very well written -- simple and clean, so it is relatively easy work with.


<a id="orgfb84d69"></a>

# How?

By using the same technique as the official CLI. By using the API description
available at `/MAAS/api/2.0/describe`. This allows us to expose the full API
exposed by the MAAS server and to keep functional parity with the CLI.

(At the moment of writing) MaaS API is self-described via an API endpoint at `${servername}:5240/MAAS/api/2.0/describe/`, 
so the Client object can be built using that description and its methods can be invoked via the syntax `client.handler.action()` -- for example,
`client.users.whoami()` would use the API endpoint url `${servername}:5240/MAAS/api/2.0/users/?op=whoami`.

Action methods for a handler would accept defined arguments, 
as well as any standard [requests](https://requests.readthedocs.io/en/latest/api/#requests.Session.request) argument: 
for example, any action for the `user` handler takes a `username` argument, 
however, `create()` action for the `users` (note the plural _s_) can also accept requests's `files` argument:

    # see client.users.create.doc for a description of expected parameters
    userdata = dict( username = 'testuser1', email = 'maas-testuser1@localhost', password = 'a_secret_passphrase', is_superuser = 0 )
    result = client.users.create( files = userdata )
    print( json.dumps( result, indent = 2 ) )
    # ( to delete the user record, invoke "client.user.delete( username = 'testuser1' )" )

( MaaS [expects][maas:api.py] extra data in a `multipart/form-data` form, and [Request(files=...)][Request] can pack it there for us -- hence the `files` argument. )

[maas:api.py]: https://github.com/cloudbase/maas/blob/master/src/maasserver/api.py
[Request]: https://requests.readthedocs.io/en/latest/api/#requests.Request
