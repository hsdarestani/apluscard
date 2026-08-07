import uuid

from django.db.models import Max

from .reconcile_legacy_database import Command as BaseReconcileCommand


class Command(BaseReconcileCommand):
    """Legacy reconciliation with deterministic PK remapping.

    The base reconciler preserves a legacy primary key when it is still free. If
    that key is already occupied by newer production data, this command assigns
    an explicit collision-free primary key instead of relying on a PostgreSQL
    sequence that may have been moved by earlier explicit inserts in the same
    reconciliation transaction.
    """

    help = BaseReconcileCommand.help + " Kollidierende AutoField-PKs werden sicher neu vergeben."

    def _raw_insert(self, model, row, *, preserve_pk=True, transforms=None):
        data = dict(row)
        if transforms:
            data.update(transforms)

        pk_field = model._meta.pk
        pk_name = pk_field.attname

        if not preserve_pk:
            internal_type = pk_field.get_internal_type()
            if internal_type in {"AutoField", "BigAutoField", "SmallAutoField"}:
                current_max = model.objects.aggregate(value=Max(pk_name))["value"] or 0
                candidate = int(current_max) + 1
                while model.objects.filter(**{pk_name: candidate}).exists():
                    candidate += 1
                data[pk_name] = candidate
            elif internal_type == "UUIDField":
                candidate = uuid.uuid4()
                while model.objects.filter(**{pk_name: candidate}).exists():
                    candidate = uuid.uuid4()
                data[pk_name] = candidate
            else:
                # The reconciler currently only needs remapping for integer and
                # UUID primary keys. Keep the legacy behaviour for other types.
                data[pk_name] = None

        obj = model()
        for field in self._fields(model):
            setattr(obj, field.attname, data.get(field.attname))
        obj.save_base(raw=True, force_insert=True, using="default")
        return obj.pk
