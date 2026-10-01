FROM frappe/erpnext:v16.34.1

USER root

COPY pyproject.toml /home/frappe/frappe-bench/apps/manase_butcher/pyproject.toml
COPY README.md /home/frappe/frappe-bench/apps/manase_butcher/README.md
COPY manase_butcher /home/frappe/frappe-bench/apps/manase_butcher/manase_butcher
COPY docker/dl-entrypoint.sh /opt/scripts/dl-entrypoint.sh
COPY manase_butcher/public /home/frappe/frappe-bench/assets/manase_butcher

RUN chmod +x /opt/scripts/dl-entrypoint.sh \
    && chown -R frappe:frappe /home/frappe/frappe-bench/apps/manase_butcher \
                              /home/frappe/frappe-bench/assets/manase_butcher

USER frappe
WORKDIR /home/frappe/frappe-bench
RUN bench pip install -e apps/manase_butcher
