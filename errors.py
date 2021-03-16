class BadAPIRequestError(BaseException):
    """Error class for when Elasticsearch API returns a 400+ error code. Usually
    because of making an API request before the Elasticsearch service is ready.

    """

    pass


class NotCreatedError(BaseException):
    """Error class for when a user or role is not acknowledged as created by the
    Elasticsearch API after a /_security/user or /_security/role request is made.

    """

    pass


class NotFoundError(BaseException):
    """Error class for when the findPassword function in utils.py is not able to find
    the requested password in the provided text.

    """

    pass