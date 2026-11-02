#!/usr/bin/env bash
# Replace the app host, launching the new one BEFORE terminating the old.
#
# Usage: deploy/roll.sh <name-prefix>      e.g. shikkhokplus-staging
#
# Called by deploy.yml twice over: once to roll out, and again to roll
# BACK when the post-deploy smoke fails -- the rollback restores the
# previous image tag and runtime env in SSM first, so the replacement
# this starts boots the previous release.
#
# **Launch before terminate** [OPS-6]. MinHealthyPercentage 100 with
# MaxHealthyPercentage 200 makes the group start the replacement while
# the current host keeps serving. The replacement waits in the launch
# lifecycle hook until its boot script proves the origin answers
# /health over verified TLS; only then is it put in service, and only
# after the warmup -- longer than the origin record's 60 s TTL, so
# CloudFront has followed the new address -- is the old host
# terminated. A replacement that never becomes ready is abandoned and
# the old host is never touched.
#
# **Why not the API's AutoRollback.** It is unsupported when the group
# uses the launch template's $Latest version, which this one does so
# that an apply never rolls the host by itself. It would also roll back
# the wrong thing: a deploy changes the image tag in SSM, not the
# launch template. deploy.yml's rollback restores the SSM state and
# calls this again, which is the rollback that actually reverts code.
set -euo pipefail

prefix=${1:?usage: roll.sh <name-prefix>}

# **Found by its Name tag, exactly.** A name-prefix match would also
# find the rehearsal host's group, whose name starts with the same
# environment prefix.
asg=$(aws autoscaling describe-auto-scaling-groups \
  --filters "Name=tag:Name,Values=$prefix-app" \
  --query 'AutoScalingGroups[0].AutoScalingGroupName' --output text)
if [ -z "$asg" ] || [ "$asg" = "None" ]; then
  echo "::error::No auto-scaling group tagged Name=$prefix-app."
  exit 1
fi
echo "Group: $asg"
[ -z "${GITHUB_OUTPUT:-}" ] || echo "asg=$asg" >> "$GITHUB_OUTPUT"

id=$(aws autoscaling start-instance-refresh \
  --auto-scaling-group-name "$asg" \
  --strategy Rolling \
  --preferences '{"MinHealthyPercentage":100,"MaxHealthyPercentage":200,"InstanceWarmup":120,"SkipMatching":false}' \
  --query 'InstanceRefreshId' --output text)
echo "Refresh: $id"

report() {
  aws autoscaling describe-instance-refreshes \
    --auto-scaling-group-name "$asg" --instance-refresh-ids "$id" \
    --query 'InstanceRefreshes[0].[Status,StatusReason]' --output text || true
  # The lifecycle hook's verdict is recorded here: "abandoned" means the
  # new host's boot script said it was not ready, or said nothing.
  aws autoscaling describe-scaling-activities \
    --auto-scaling-group-name "$asg" --max-items 5 \
    --query 'Activities[].[StartTime,StatusCode,StatusMessage,Description]' \
    --output text || true
}

# 40 minutes: the hook's own 20-minute timeout, one retry by the group,
# and the warmup.
status=""
for _ in $(seq 1 120); do
  status=$(aws autoscaling describe-instance-refreshes \
    --auto-scaling-group-name "$asg" --instance-refresh-ids "$id" \
    --query 'InstanceRefreshes[0].Status' --output text)
  case "$status" in
    Successful)
      echo "Refresh complete: the new host is in service."
      exit 0 ;;
    Failed|Cancelled|RollbackSuccessful|RollbackFailed)
      echo "::error::Instance refresh $status. The previous host is terminated only after its replacement is in service, so unless the refresh got that far it is still serving."
      report
      exit 1 ;;
  esac
  sleep 20
done

echo "::error::Refresh $id did not finish in 40 minutes; cancelling it."
aws autoscaling cancel-instance-refresh --auto-scaling-group-name "$asg" || true
report
exit 1
