from openai import OpenAI


def generate_sanri_response(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_input: str,
) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        temperature=0.9,
        max_tokens=500,
    )

    text_resp = (completion.choices[0].message.content or "").strip()

    if not text_resp:
        text_resp = "Sanrı seni duydu."

    return text_resp