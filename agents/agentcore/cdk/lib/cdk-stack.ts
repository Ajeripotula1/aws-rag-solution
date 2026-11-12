import { AgentCoreApplication, type AgentCoreApplicationProps } from '@aws/agentcore-cdk';
import { Stack, type StackProps, aws_iam as iam, aws_lambda as lambda } from 'aws-cdk-lib';
import { Construct } from 'constructs';

// Must match the runtime's envVars in agentcore/agentcore.json.
// ORDERS_LAMBDA_NAME comes from infra/stacks/tools_stack.py; KB_ID from the Bedrock console.
const RUNTIME_NAME = 'agents';
const ORDERS_LAMBDA_NAME = 'aws-rag-solution-orders';
const KB_ID = 'SCFYIOZDOU';

export interface AgentCoreStackProps extends StackProps {
  /** Props for the AgentCore application, produced by transformAgentCoreJson from agentcore/agentcore.json. */
  application: AgentCoreApplicationProps;
}

/**
 * The stack the AgentCore CLI deploys. Everything declared in agentcore/agentcore.json is
 * created by the AgentCoreApplication construct. Add your own resources below it and wire
 * them to your runtimes and harnesses through the application's accessors.
 */
export class AgentCoreStack extends Stack {
  public readonly application: AgentCoreApplication;

  constructor(scope: Construct, id: string, props: AgentCoreStackProps) {
    super(scope, id, props);
    this.application = new AgentCoreApplication(this, 'Application', props.application);
    const runtime = this.application.runtime(RUNTIME_NAME);

    // Orders tools: account_agent and refund_agent call the orders Lambda.
    lambda.Function.fromFunctionName(this, 'OrdersFunction', ORDERS_LAMBDA_NAME).grantInvoke(runtime);

    // FAQ tool: faq_agent calls bedrock-agent-runtime Retrieve on the Knowledge Base.
    iam.Grant.addToPrincipal({
      grantee: runtime,
      actions: ['bedrock:Retrieve'],
      resourceArns: [
        Stack.of(this).formatArn({ service: 'bedrock', resource: 'knowledge-base', resourceName: KB_ID }),
      ],
    });

    // Example: give a runtime a DynamoDB table.
    //
    // import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
    // const orders = new dynamodb.Table(this, 'Orders', {
    //   partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
    // });
    // const checkout = this.application.runtime('checkout'); // or .harness('support')
    // checkout.grantReadWrite(orders);
    // checkout.addEnvironmentVariable('ORDERS_TABLE', orders.tableName);
  }
}
