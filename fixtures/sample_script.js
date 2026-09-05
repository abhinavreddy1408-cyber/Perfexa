import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 200,
  duration: '12s',
  thresholds: {
    'http_req_duration': ['p(95)<200'],
    'http_req_failed': ['rate<0.1'],
  },
};

const BASE_URL = 'http://127.0.0.1:8001';
const PAYLOADS = [
  { field1: 'value1', field2: 'value2' },
  { field1: 'value3', field2: 'value4' },
  { field1: 'value5', field2: 'value6' },
  { field1: 'value7', field2: 'value8' },
  { field1: 'value9', field2: 'value10' },
];

export default function () {
  const payload = PAYLOADS[Math.floor(Math.random() * PAYLOADS.length)];
  const res = http.post(`${BASE_URL}/api/heavy`, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
  });
  check(res, {
    'status is 200': (r) => r.status === 200,
    'not 503 overloaded': (r) => r.status !== 503,
  });
  sleep(0.2);
}