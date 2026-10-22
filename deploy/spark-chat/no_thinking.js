// Forces Qwen3's non-thinking mode on every chat request, whatever the caller sent, then forwards it to vLLM.
// The host vLLM defaults to it too (--default-chat-template-kwargs); this keeps it true if that flag changes.
async function forward(r) {
    let body;
    try {
        body = JSON.parse(r.requestText);
    } catch (e) {
        body = null;
    }
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
        r.headersOut['Content-Type'] = 'application/json';
        r.return(400, '{"error":"body must be a JSON object"}');
        return;
    }
    const kwargs = (body.chat_template_kwargs && typeof body.chat_template_kwargs === 'object')
        ? body.chat_template_kwargs : {};
    kwargs.enable_thinking = false;
    body.chat_template_kwargs = kwargs;
    const reply = await r.subrequest('/vllm/v1/chat/completions', {method: 'POST', body: JSON.stringify(body)});
    r.headersOut['Content-Type'] = reply.headersOut['Content-Type'] || 'application/json';
    r.return(reply.status, reply.responseText);
}

export default {forward};
