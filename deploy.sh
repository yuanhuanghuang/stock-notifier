#!/bin/bash
set -e

REGION="us-east-1"
FUNCTION_NAME="stock-notifier"
LAYER_NAME="stock-notifier-deps"
ROLE_NAME="stock-notifier-lambda-role"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region $REGION)
echo "Account: $ACCOUNT_ID | Region: $REGION"

# --- 1. Build dependencies layer (Linux x86_64 compatible) ---
echo "Building dependencies layer..."
rm -rf layer_build && mkdir -p layer_build/python
pip install \
  --platform manylinux2014_x86_64 \
  --target=layer_build/python \
  --implementation cp \
  --python-version 313 \
  --only-binary=:all: \
  --upgrade \
  -r requirements.txt -q
cd layer_build && zip -r ../layer.zip python/ -q && cd ..
rm -rf layer_build
echo "  Layer size: $(du -sh layer.zip | cut -f1)"

# --- 2. Zip function code ---
echo "Packaging function code..."
zip -r function.zip . \
  -x "*.pyc" -x "__pycache__/*" -x ".venv/*" \
  -x "layer.zip" -x "function.zip" \
  -x ".env" -x ".git/*" -x "deploy.sh" -q
echo "  Function size: $(du -sh function.zip | cut -f1)"

# --- 3. Create IAM role ---
if aws iam get-role --role-name $ROLE_NAME &>/dev/null; then
  echo "IAM role exists."
  ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)
else
  echo "Creating IAM role..."
  ROLE_ARN=$(aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document \
      '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    --query 'Role.Arn' --output text)
  aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "  Waiting for role to propagate..."
  sleep 10
fi
echo "  Role: $ROLE_ARN"

# --- 4. Upload layer to S3, then publish ---
S3_BUCKET="stock-notifier-deploy-$ACCOUNT_ID"
echo "Uploading layer to S3..."
aws s3 mb s3://$S3_BUCKET --region $REGION 2>/dev/null || true
aws s3 cp layer.zip s3://$S3_BUCKET/layer.zip --region $REGION
LAYER_ARN=$(aws lambda publish-layer-version \
  --layer-name $LAYER_NAME \
  --content S3Bucket=$S3_BUCKET,S3Key=layer.zip \
  --compatible-runtimes python3.13 \
  --compatible-architectures x86_64 \
  --query 'LayerVersionArn' --output text \
  --region $REGION)
echo "  Layer ARN: $LAYER_ARN"

# --- 5. Build env vars JSON (avoids shell quoting issues) ---
python3 - <<'PYEOF'
import json, os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")
env = {
    "Variables": {
        "ANTHROPIC_API_KEY":  os.environ["ANTHROPIC_API_KEY"],
        "GMAIL_SENDER":       os.environ["GMAIL_SENDER"],
        "GMAIL_APP_PASSWORD": os.environ["GMAIL_APP_PASSWORD"],
        "EMAIL_RECIPIENTS":   os.environ.get("EMAIL_RECIPIENTS", "yuanhuan@usc.edu"),
        "TOP_N":              os.environ.get("TOP_N", "10"),
    }
}
with open("/tmp/lambda_env.json", "w") as f:
    json.dump(env, f)
print("  Env vars written to /tmp/lambda_env.json")
PYEOF

# --- 6. Create or update Lambda function ---
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
  echo "Updating Lambda function..."
  aws lambda update-function-code \
    --function-name $FUNCTION_NAME \
    --zip-file fileb://function.zip \
    --region $REGION
  aws lambda wait function-updated --function-name $FUNCTION_NAME --region $REGION
  aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --layers $LAYER_ARN \
    --environment file:///tmp/lambda_env.json \
    --region $REGION
else
  echo "Creating Lambda function..."
  aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.13 \
    --role $ROLE_ARN \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://function.zip \
    --layers $LAYER_ARN \
    --timeout 900 \
    --memory-size 512 \
    --environment file:///tmp/lambda_env.json \
    --architectures x86_64 \
    --region $REGION
fi

aws lambda wait function-active --function-name $FUNCTION_NAME --region $REGION
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME \
  --region $REGION --query 'Configuration.FunctionArn' --output text)
echo "  Function ARN: $FUNCTION_ARN"

# --- 7. EventBridge schedules ---
echo "Setting up EventBridge schedules..."

aws lambda add-permission \
  --function-name $FUNCTION_NAME \
  --statement-id "allow-eventbridge" \
  --action "lambda:InvokeFunction" \
  --principal "events.amazonaws.com" \
  --region $REGION 2>/dev/null || true

# Morning: 10:30 AM ET (EDT=UTC-4) → 14:30 UTC
aws events put-rule \
  --name "stock-notifier-morning" \
  --schedule-expression "cron(30 14 ? * MON-FRI *)" \
  --state ENABLED --region $REGION
aws events put-targets \
  --rule "stock-notifier-morning" \
  --targets "Id=lambda,Arn=$FUNCTION_ARN" \
  --region $REGION

# Afternoon: 2:30 PM ET (EDT=UTC-4) → 18:30 UTC
aws events put-rule \
  --name "stock-notifier-afternoon" \
  --schedule-expression "cron(30 18 ? * MON-FRI *)" \
  --state ENABLED --region $REGION
aws events put-targets \
  --rule "stock-notifier-afternoon" \
  --targets "Id=lambda,Arn=$FUNCTION_ARN" \
  --region $REGION

rm -f layer.zip function.zip /tmp/lambda_env.json

echo ""
echo "Deployed! Stock Notifier is live."
echo "  Morning:   10:30 AM ET, Mon-Fri"
echo "  Afternoon:  2:30 PM ET, Mon-Fri"
echo "  Logs: https://console.aws.amazon.com/cloudwatch/home?region=$REGION#logsV2:log-groups/log-group/%2Faws%2Flambda%2F$FUNCTION_NAME"
