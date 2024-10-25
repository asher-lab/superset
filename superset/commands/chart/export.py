# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
# isort:skip_file

import logging
from collections.abc import Iterator
from typing import Callable

import yaml

from superset.commands.chart.exceptions import ChartNotFoundError
from superset.daos.chart import ChartDAO
from superset.commands.dataset.export import ExportDatasetsCommand
from superset.commands.export.models import ExportModelsCommand
from superset.commands.tag.export import ExportTagsCommand
from superset.models.slice import Slice
from superset.utils.dict_import_export import EXPORT_VERSION
from superset.utils.file import get_filename
from superset.utils import json

logger = logging.getLogger(__name__)


# keys present in the standard export that are not needed
REMOVE_KEYS = ["datasource_type", "datasource_name", "url_params"]


class ExportChartsCommand(ExportModelsCommand):
    dao = ChartDAO
    not_found = ChartNotFoundError

    @staticmethod
    def _file_name(model: Slice) -> str:
        file_name = get_filename(model.slice_name, model.id)
        return f"charts/{file_name}.yaml"

    @staticmethod
    def _file_content(model: Slice) -> str:
        payload = model.export_to_dict(
            recursive=False,
            include_parent_ref=False,
            include_defaults=True,
            export_uuids=True,
        )
        # TODO (betodealmeida): move this logic to export_to_dict once this
        #  becomes the default export endpoint
        payload = {
            key: value for key, value in payload.items() if key not in REMOVE_KEYS
        }

        if payload.get("params"):
            try:
                payload["params"] = json.loads(payload["params"])
            except json.JSONDecodeError:
                logger.info("Unable to decode `params` field: %s", payload["params"])

        payload["version"] = EXPORT_VERSION
        if model.table:
            payload["dataset_uuid"] = str(model.table.uuid)

        # Fetch tags from the database
        tags = (
            model.tags  # Assuming `tags` is a relationship in the `Slice` model
            if hasattr(model, "tags") else []
        )
        # Filter out any tags that contain "type:" in their name
        payload["tag"] = [tag.name for tag in tags if "type:" not in tag.name]
        
        file_content = yaml.safe_dump(payload, sort_keys=False)
        return file_content

    # Add a parameter for should_export_tags in the constructor
    def __init__(self, chart_ids, should_export_tags=True):
        super().__init__(chart_ids)
        self.should_export_tags = should_export_tags
        

    # Change to an instance method
    def _export(
        self, model: Slice, export_related: bool = True
    ) -> Iterator[tuple[str, Callable[[], str]]]:
        yield (
            ExportChartsCommand._file_name(model),
            lambda: ExportChartsCommand._file_content(model),
        )

        if model.table and export_related:
            yield from ExportDatasetsCommand([model.table.id]).run()


        if export_related and self.should_export_tags:
            chart_id = model.id
            yield from ExportTagsCommand._export(chart_ids=[chart_id])