"""Tests for the shared SQLAlchemy metadata conventions."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from bid_system.platform.database.models import OrmBase


def test_metadata_generates_stable_constraint_names() -> None:
    parent = Table(
        "parent",
        OrmBase.metadata,
        Column("id", Integer, primary_key=True),
        schema="example",
    )
    child = Table(
        "child",
        OrmBase.metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", ForeignKey(parent.c.id), nullable=False),
        schema="example",
    )

    primary_key = child.primary_key
    foreign_key = next(iter(child.foreign_key_constraints))

    assert primary_key.name == "pk_child"
    assert foreign_key.name == "fk_child_parent_id_parent"
