import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', None),
            'method': getattr(record, 'method', None),
            'path': getattr(record, 'path', None),
            'status_code': getattr(record, 'status_code', None),
            'duration_ms': getattr(record, 'duration_ms', None),
        }
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps({key: value for key, value in payload.items() if value is not None})
