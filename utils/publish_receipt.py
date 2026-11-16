"""Optional receipts for web tasks; existing CLI callers need no callbacks."""


def attempted(uploader):
    uploader.publish_attempted = True
    callback = getattr(uploader, "on_publish_attempt", None)
    if callback:
        callback()


def stop_web_resubmission(uploader):
    """An uncertain submit ends a Web task; CLI keeps its existing behavior."""
    if getattr(uploader, "on_publish_attempt", None) and getattr(
        uploader, "publish_attempted", False
    ):
        raise RuntimeError("已尝试提交发布，请先到平台核实结果")


def confirmed(uploader):
    uploader.publish_confirmed = True
    callback = getattr(uploader, "on_publish_confirmed", None)
    if callback:
        try:
            callback()
        except Exception:
            # The platform already accepted the post. Never re-enter its submit
            # loop merely because persisting a receipt temporarily failed.
            import logging

            logging.getLogger(__name__).exception("平台已确认发布，保存回执失败")
