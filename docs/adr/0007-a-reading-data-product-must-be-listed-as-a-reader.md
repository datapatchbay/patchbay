# A reading data product must be listed as a reader

An output port lists its readers: plain strings that are used as warehouse role names as written, and `product: <data product>` entries that map to that data product's role. A data product that declares an input port on someone else's output port does not get access by doing so. It must also appear in that port's readers, and `dpb validate` fails when it does not. We chose this so that the owner of a port approves each new reader in a pull request, and so that the access a data product needs is granted from the same list as everyone else's.

These are two separate facts. The readers list of an output port says who can read it. The input ports of the other data products say which data products are reading it. The second is never written on the output port: it is derived by going over every data product's input ports, so there is no separate list of consumers.

## Considered options

- **Access follows from the input port.** Rejected: any data product could give itself access to any port.
- **Typed entries (`group:`, `user:`, `role:`).** Rejected: in the warehouse they are all roles, so the type adds typing and no meaning.
- **A `consumers` list for BI apps next to `readers`.** Rejected: a second list that nothing enforces.
