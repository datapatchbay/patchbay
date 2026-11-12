{#
  Build a model in the schema its properties name, as written. dbt's default would build `<target schema>_<schema>`,
  and the views and grants of the output port name the private schema without a prefix.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name | trim if custom_schema_name is not none else target.schema }}
{%- endmacro %}
