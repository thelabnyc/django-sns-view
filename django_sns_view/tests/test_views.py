from copy import deepcopy
from unittest.mock import patch
import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotAllowed
from django.test import RequestFactory
from django.test.utils import override_settings

from django_sns_view.tests.helpers import SNSBaseTest
from django_sns_view.tests.test_data.notifications import SNS_NOTIFICATION
from django_sns_view.views import SNSEndpoint


@override_settings(SNS_VERIFY_CERTIFICATE=False)
class SNSEndpointTestCase(SNSBaseTest):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.post("/")
        self.endpoint = SNSEndpoint.as_view()
        self.request.META["HTTP_X_AMZ_SNS_TOPIC_ARN"] = settings.SNS_STORY_TOPIC_ARN[0]
        self.request.META["HTTP_X_AMZ_SNS_MESSAGE_TYPE"] = "Notification"

    def test_non_post_httpnotallowed(self):
        """
        Test that GET requests to the endpoint return a
        HttpResponseNotAllowed
        """
        request = self.factory.get("/")
        response = self.endpoint(request)
        self.assertIsInstance(response, HttpResponseNotAllowed)

    @patch.object(
        SNSEndpoint,
        "handle_message",
        lambda _, message, notification: HttpResponse("OK"),
    )
    def test_success(self):
        """Test a successful request"""
        self.request._body = json.dumps(self.sns_notification)
        response = self.endpoint(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("ascii"), "OK")

    @override_settings(
        SNS_TEST_TOPIC_ARN=["arn:aws:sns:us-west-2:123456789012:MyTopic"]
    )
    @patch.object(SNSEndpoint, "topic_settings_key", "SNS_TEST_TOPIC_ARN")
    def test_no_topic_header(self):
        """Test the results if the request does not have a topic header"""
        request = self.factory.post("/")
        request.META["HTTP_X_AMZ_SNS_MESSAGE_TYPE"] = "Notification"
        request._body = json.dumps(self.sns_notification)
        response = self.endpoint(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode("ascii"), "No TopicArn Header")

    @override_settings(SNS_TEST_TOPIC_ARN=["Diddly Doo"])
    @patch.object(SNSEndpoint, "topic_settings_key", "SNS_TEST_TOPIC_ARN")
    def test_bad_topic(self):
        """Test the response if the topic does not match the settings"""
        self.request._body = json.dumps(self.sns_notification)
        response = self.endpoint(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode("ascii"), "Bad Topic")

    def test_invalid_notification_json(self):
        """Test if the notification does not have a JSON body"""
        self.request._body = "This Is Not JSON"
        response = self.endpoint(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode("ascii"), "Not Valid JSON")

    def test_invalid_notification_type(self):
        """Test an unknown notification type"""
        request = self.factory.post("/")
        request.META["HTTP_X_AMZ_SNS_TOPIC_ARN"] = settings.SNS_STORY_TOPIC_ARN[0]
        request.META["HTTP_X_AMZ_SNS_MESSAGE_TYPE"] = "Invalid"
        request._body = json.dumps(self.sns_notification)
        response = self.endpoint(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode("ascii"), "Invalid Notification Type")

    def test_bad_certificate_url(self):
        """Test an unknown certificate hostname"""
        notification = deepcopy(SNS_NOTIFICATION)
        notification["SigningCertURL"] = "https://baddomain.com/cert.pem"
        self.request._body = json.dumps(notification)
        response = self.endpoint(self.request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.content.decode("ascii"), "Improper Certificate Location"
        )

    @patch("django_sns_view.views.confirm_subscription")
    def test_confirm_subscription_called(self, mock):
        """
        Test that confirm_subscription is called when sns
        sends a SubscriptionConfirmation notification
        """
        mock.return_value = "Confirmed"
        self.request.META["HTTP_X_AMZ_SNS_MESSAGE_TYPE"] = "SubscriptionConfirmation"
        self.request._body = json.dumps(self.sns_confirmation)
        response = self.endpoint(self.request)
        self.assertTrue(mock.called)
        self.assertEqual(response, "Confirmed")

    def test_unsubscribe_confirmation_not_handled(self):
        """Test that an unsubscribe notification is properly ignored"""
        self.request.META["HTTP_X_AMZ_SNS_MESSAGE_TYPE"] = "UnsubscribeConfirmation"
        self.request._body = json.dumps(self.sns_notification)
        response = self.endpoint(self.request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content.decode("ascii"), "UnsubscribeConfirmation Not Handled"
        )

    @patch.object(SNSEndpoint, "handle_message")
    def test_handle_message_sucessfully_called(self, mock):
        """
        Test that the handle message method is called successfully,
        and that it has the right arguments passed.
        """
        mock.return_value = True
        self.request._body = json.dumps(self.sns_notification)
        response = self.endpoint(self.request)
        mock.assert_called_once_with(
            SNS_NOTIFICATION.get("Message"), json.loads(json.dumps(SNS_NOTIFICATION))
        )
        self.assertEqual(response.status_code, 200)
