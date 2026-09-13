from .process_layout.Edge import Edge


class ObjectEdge(Edge):
    """An edge of one object type's graph; its key is (source, target, object_type)."""

    def __init__(self, snode, enode, object_type, freq=None, org_e=None):
        super().__init__(snode, enode, freq=freq, org_e=org_e)
        self.key = (snode.name, enode.name, object_type)
        self.object_type = object_type

    @classmethod
    def gen_key(cls, key, ot):
        return (key[0], key[1], ot)

    def get_string_key(self):
        return '-'.join(self.key)
