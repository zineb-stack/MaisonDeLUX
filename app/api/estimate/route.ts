import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  try {
    const response = await fetch(`${process.env.INFERENCE_API_URL || 'http://127.0.0.1:5000'}/api/estimate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: await request.text(),
      signal: AbortSignal.timeout(10000),
      cache: 'no-store',
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ error: "Le service d'estimation est momentanément indisponible." }, { status: 503 });
  }
}
