<?php
$input = file_get_contents("php://input");
// Get the secret path from your bot token to make the URL secure
//$bot_token = ""; // It's safer to get this from an env file
//$url_path = substr($bot_token, strrpos($bot_token, ':') + 1);

// Forward the data to the Python bot listening locally on port 8443
$ch = curl_init("http://127.0.0.1:8000/webhook");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, $input);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Content-Type: application/json',
]);
$response = curl_exec($ch);
curl_close($ch);
echo $response;
?>
