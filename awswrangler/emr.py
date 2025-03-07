"""
Module to handle all utilities related to EMR (Elastic Map Reduce)
https://aws.amazon.com/emr/
"""
from typing import Optional, List, Dict
import logging
import json

from boto3 import client  # type: ignore

logger = logging.getLogger(__name__)


class EMR:
    """
    EMR representation
    """
    def __init__(self, session):
        self._session = session
        self._client_emr: client = session.boto3_session.client(service_name="emr", config=session.botocore_config)

    @staticmethod
    def _build_cluster_args(**pars):
        args: Dict = {
            "Name": pars["cluster_name"],
            "LogUri": pars["logging_s3_path"],
            "ReleaseLabel": pars["emr_release"],
            "VisibleToAllUsers": pars["visible_to_all_users"],
            "JobFlowRole": pars["emr_ec2_role"],
            "ServiceRole": pars["emr_role"],
            "Instances": {
                "KeepJobFlowAliveWhenNoSteps": True,
                "TerminationProtected": False,
                "Ec2SubnetId": pars["subnet_id"],
                "InstanceFleets": []
            }
        }

        # EC2 Key Pair
        if pars["key_pair_name"] is not None:
            args["Instances"]["Ec2KeyName"] = pars["key_pair_name"]

        # Security groups
        if pars["security_group_master"] is not None:
            args["Instances"]["EmrManagedMasterSecurityGroup"] = pars["security_group_master"]
        if pars["security_groups_master_additional"] is not None:
            args["Instances"]["AdditionalMasterSecurityGroups"] = pars["security_groups_master_additional"]
        if pars["security_group_slave"] is not None:
            args["Instances"]["EmrManagedSlaveSecurityGroup"] = pars["security_group_slave"]
        if pars["security_groups_slave_additional"] is not None:
            args["Instances"]["AdditionalSlaveSecurityGroups"] = pars["security_groups_slave_additional"]
        if pars["security_group_service_access"] is not None:
            args["Instances"]["ServiceAccessSecurityGroup"] = pars["security_group_service_access"]

        # Configurations
        if pars["python3"] or pars["spark_glue_catalog"] or pars["hive_glue_catalog"] or pars["presto_glue_catalog"]:
            args["Configurations"]: List = []
            if pars["python3"]:
                args["Configurations"].append({
                    "Classification":
                    "spark-env",
                    "Properties": {},
                    "Configurations": [{
                        "Classification": "export",
                        "Properties": {
                            "PYSPARK_PYTHON": "/usr/bin/python3"
                        },
                        "Configurations": []
                    }]
                })
            if pars["spark_glue_catalog"]:
                args["Configurations"].append({
                    "Classification": "spark-hive-site",
                    "Properties": {
                        "hive.metastore.client.factory.class":
                        "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",
                    },
                    "Configurations": []
                })
            if pars["hive_glue_catalog"]:
                args["Configurations"].append({
                    "Classification": "hive-site",
                    "Properties": {
                        "hive.metastore.client.factory.class":
                        "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory"
                    },
                    "Configurations": []
                })
            if pars["presto_glue_catalog"]:
                args["Configurations"].append({
                    "Classification": "presto-connector-hive",
                    "Properties": {
                        "hive.metastore.glue.datacatalog.enabled": "true"
                    },
                    "Configurations": []
                })

        # Applications
        if pars["applications"]:
            args["Applications"]: List[Dict[str, str]] = [{"Name": x} for x in pars["applications"]]

        # Bootstraps
        if pars["bootstraps_paths"]:
            args["BootstrapActions"]: List[Dict] = [{
                "Name": x,
                "ScriptBootstrapAction": {
                    "Path": x
                }
            } for x in pars["bootstraps_paths"]]

        # Debugging
        if pars["debugging"]:
            args["Steps"]: List[Dict] = [{
                "Name": "Setup Hadoop Debugging",
                "ActionOnFailure": "TERMINATE_CLUSTER",
                "HadoopJarStep": {
                    "Jar": "command-runner.jar",
                    "Args": ["state-pusher-script"]
                }
            }]

        # Master Instance Fleet
        timeout_action_master: str = "SWITCH_TO_ON_DEMAND" if pars[
            "spot_timeout_to_on_demand_master"] else "TERMINATE_CLUSTER"
        fleet_master: Dict = {
            "Name":
            "MASTER",
            "InstanceFleetType":
            "MASTER",
            "TargetOnDemandCapacity":
            pars["instance_num_on_demand_master"],
            "TargetSpotCapacity":
            pars["instance_num_spot_master"],
            "InstanceTypeConfigs": [
                {
                    "InstanceType": pars["instance_type_master"],
                    "WeightedCapacity": 1,
                    "BidPriceAsPercentageOfOnDemandPrice": pars["spot_bid_percentage_of_on_demand_master"],
                    "EbsConfiguration": {
                        "EbsBlockDeviceConfigs": [{
                            "VolumeSpecification": {
                                "SizeInGB": pars["instance_ebs_size_master"],
                                "VolumeType": "gp2"
                            },
                            "VolumesPerInstance": 1
                        }],
                        "EbsOptimized":
                        True
                    },
                },
            ],
        }
        if pars["instance_num_spot_master"] > 0:
            fleet_master["LaunchSpecifications"]: Dict = {
                "SpotSpecification": {
                    "TimeoutDurationMinutes": pars["spot_provisioning_timeout_master"],
                    "TimeoutAction": timeout_action_master,
                }
            }
        args["Instances"]["InstanceFleets"].append(fleet_master)

        # Core Instance Fleet
        timeout_action_core = "SWITCH_TO_ON_DEMAND" if pars["spot_timeout_to_on_demand_core"] else "TERMINATE_CLUSTER"
        fleet_core: Dict = {
            "Name":
            "CORE",
            "InstanceFleetType":
            "CORE",
            "TargetOnDemandCapacity":
            pars["instance_num_on_demand_core"],
            "TargetSpotCapacity":
            pars["instance_num_spot_core"],
            "InstanceTypeConfigs": [
                {
                    "InstanceType": pars["instance_type_core"],
                    "WeightedCapacity": 1,
                    "BidPriceAsPercentageOfOnDemandPrice": pars["spot_bid_percentage_of_on_demand_core"],
                    "EbsConfiguration": {
                        "EbsBlockDeviceConfigs": [{
                            "VolumeSpecification": {
                                "SizeInGB": pars["instance_ebs_size_core"],
                                "VolumeType": "gp2"
                            },
                            "VolumesPerInstance": 1
                        }],
                        "EbsOptimized":
                        True
                    },
                },
            ],
        }
        if pars["instance_num_spot_core"] > 0:
            fleet_core["LaunchSpecifications"]: Dict = {
                "SpotSpecification": {
                    "TimeoutDurationMinutes": pars["spot_provisioning_timeout_core"],
                    "TimeoutAction": timeout_action_core,
                }
            }
        args["Instances"]["InstanceFleets"].append(fleet_core)

        # # Task Instance Fleet
        timeout_action_task: str = "SWITCH_TO_ON_DEMAND" if pars[
            "spot_timeout_to_on_demand_task"] else "TERMINATE_CLUSTER"
        fleet_task: Dict = {
            "Name":
            "TASK",
            "InstanceFleetType":
            "TASK",
            "TargetOnDemandCapacity":
            pars["instance_num_on_demand_task"],
            "TargetSpotCapacity":
            pars["instance_num_spot_task"],
            "InstanceTypeConfigs": [
                {
                    "InstanceType": pars["instance_type_task"],
                    "WeightedCapacity": 1,
                    "BidPriceAsPercentageOfOnDemandPrice": pars["spot_bid_percentage_of_on_demand_task"],
                    "EbsConfiguration": {
                        "EbsBlockDeviceConfigs": [{
                            "VolumeSpecification": {
                                "SizeInGB": pars["instance_ebs_size_task"],
                                "VolumeType": "gp2"
                            },
                            "VolumesPerInstance": 1
                        }],
                        "EbsOptimized":
                        True
                    },
                },
            ],
        }
        if pars["instance_num_spot_task"] > 0:
            fleet_task["LaunchSpecifications"]: Dict = {
                "SpotSpecification": {
                    "TimeoutDurationMinutes": pars["spot_provisioning_timeout_task"],
                    "TimeoutAction": timeout_action_task,
                }
            }
        args["Instances"]["InstanceFleets"].append(fleet_task)

        logger.info(f"args: \n{json.dumps(args, default=str, indent=4)}")
        return args

    def create_cluster(self,
                       cluster_name: str,
                       logging_s3_path: str,
                       emr_release: str,
                       subnet_id: str,
                       emr_ec2_role: str,
                       emr_role: str,
                       instance_type_master: str,
                       instance_type_core: str,
                       instance_type_task: str,
                       instance_ebs_size_master: int,
                       instance_ebs_size_core: int,
                       instance_ebs_size_task: int,
                       instance_num_on_demand_master: int,
                       instance_num_on_demand_core: int,
                       instance_num_on_demand_task: int,
                       instance_num_spot_master: int,
                       instance_num_spot_core: int,
                       instance_num_spot_task: int,
                       spot_bid_percentage_of_on_demand_master: int,
                       spot_bid_percentage_of_on_demand_core: int,
                       spot_bid_percentage_of_on_demand_task: int,
                       spot_provisioning_timeout_master: int,
                       spot_provisioning_timeout_core: int,
                       spot_provisioning_timeout_task: int,
                       spot_timeout_to_on_demand_master: bool = True,
                       spot_timeout_to_on_demand_core: bool = True,
                       spot_timeout_to_on_demand_task: bool = True,
                       python3: bool = True,
                       spark_glue_catalog: bool = True,
                       hive_glue_catalog: bool = True,
                       presto_glue_catalog: bool = True,
                       bootstraps_paths: Optional[List[str]] = None,
                       debugging: bool = True,
                       applications: Optional[List[str]] = None,
                       visible_to_all_users: bool = True,
                       key_pair_name: Optional[str] = None,
                       security_group_master: Optional[str] = None,
                       security_groups_master_additional: Optional[List[str]] = None,
                       security_group_slave: Optional[str] = None,
                       security_groups_slave_additional: Optional[List[str]] = None,
                       security_group_service_access: Optional[str] = None):
        """
        Create a EMR cluster with instance fleets configuration
        https://docs.aws.amazon.com/emr/latest/ManagementGuide/emr-instance-fleet.html
        :param cluster_name: Cluster name
        :param logging_s3_path: Logging s3 path (e.g. s3://BUCKET_NAME/DIRECTORY_NAME/)
        :param emr_release: EMR release (e.g. emr-5.27.0)
        :param subnet_id: VPC subnet ID
        :param emr_ec2_role: IAM role name
        :param emr_role: IAM role name
        :param instance_type_master: EC2 instance type
        :param instance_type_core: EC2 instance type
        :param instance_type_task: EC2 instance type
        :param instance_ebs_size_master: Size of EBS in GB
        :param instance_ebs_size_core: Size of EBS in GB
        :param instance_ebs_size_task: Size of EBS in GB
        :param instance_num_on_demand_master: Number of on demand instances
        :param instance_num_on_demand_core: Number of on demand instances
        :param instance_num_on_demand_task: Number of on demand instances
        :param instance_num_spot_master: Number of spot instances
        :param instance_num_spot_core: Number of spot instances
        :param instance_num_spot_task: Number of spot instances
        :param spot_bid_percentage_of_on_demand_master: The bid price, as a percentage of On-Demand price
        :param spot_bid_percentage_of_on_demand_core: The bid price, as a percentage of On-Demand price
        :param spot_bid_percentage_of_on_demand_task: The bid price, as a percentage of On-Demand price
        :param spot_provisioning_timeout_master: The spot provisioning timeout period in minutes. If Spot instances are not provisioned within this time period, the TimeOutAction is taken. Minimum value is 5 and maximum value is 1440. The timeout applies only during initial provisioning, when the cluster is first created.
        :param spot_provisioning_timeout_core: The spot provisioning timeout period in minutes. If Spot instances are not provisioned within this time period, the TimeOutAction is taken. Minimum value is 5 and maximum value is 1440. The timeout applies only during initial provisioning, when the cluster is first created.
        :param spot_provisioning_timeout_task: The spot provisioning timeout period in minutes. If Spot instances are not provisioned within this time period, the TimeOutAction is taken. Minimum value is 5 and maximum value is 1440. The timeout applies only during initial provisioning, when the cluster is first created.
        :param spot_timeout_to_on_demand_master: After a provisioning timeout should the cluster switch to on demand or shutdown?
        :param spot_timeout_to_on_demand_core: After a provisioning timeout should the cluster switch to on demand or shutdown?
        :param spot_timeout_to_on_demand_task: After a provisioning timeout should the cluster switch to on demand or shutdown?
        :param python3: Python 3 Enabled?
        :param spark_glue_catalog: Spark integration with Glue Catalog?
        :param hive_glue_catalog: Hive integration with Glue Catalog?
        :param presto_glue_catalog: Presto integration with Glue Catalog?
        :param bootstraps_paths: Bootstraps paths (e.g ["s3://BUCKET_NAME/script.sh"])
        :param debugging: Debugging enabled?
        :param applications: List of applications (e.g ["Hadoop", "Spark", "Ganglia", "Hive"])
        :param visible_to_all_users: True or False
        :param key_pair_name: Key pair name (string)
        :param security_group_master: The identifier of the Amazon EC2 security group for the master node.
        :param security_groups_master_additional: A list of additional Amazon EC2 security group IDs for the master node.
        :param security_group_slave: The identifier of the Amazon EC2 security group for the core and task nodes.
        :param security_groups_slave_additional: A list of additional Amazon EC2 security group IDs for the core and task nodes.
        :param security_group_service_access: The identifier of the Amazon EC2 security group for the Amazon EMR service to access clusters in VPC private subnets.
        :return: Cluster ID (string)
        """
        args = EMR._build_cluster_args(**locals())
        response = self._client_emr.run_job_flow(**args)
        logger.info(f"response: \n{json.dumps(response, default=str, indent=4)}")
        return response["JobFlowId"]

    def get_cluster_state(self, cluster_id: str) -> str:
        """
        Get the EMR cluster state
        Possible states: 'STARTING', 'BOOTSTRAPPING', 'RUNNING', 'WAITING', 'TERMINATING', 'TERMINATED', 'TERMINATED_WITH_ERRORS'
        :param cluster_id: EMR Cluster ID
        :return: State (string)
        """
        response: Dict = self._client_emr.describe_cluster(ClusterId=cluster_id)
        logger.info(f"response: \n{json.dumps(response, default=str, indent=4)}")
        return response["Cluster"]["Status"]["State"]

    def terminate_cluster(self, cluster_id: str) -> None:
        """
        Terminate the cluster
        :param cluster_id: EMR Cluster ID
        :return: None
        """
        response: Dict = self._client_emr.terminate_job_flows(JobFlowIds=[
            cluster_id,
        ])
        logger.info(f"response: \n{json.dumps(response, default=str, indent=4)}")

    def submit_step(self, cluster_id: str, name: str, cmd: str, action_on_failure: str = "CONTINUE") -> str:
        """
        Submit new job in the EMR Cluster
        :param cluster_id: EMR Cluster ID
        :param name: Step name
        :param cmd: Command to be executed
        :param action_on_failure: 'TERMINATE_JOB_FLOW', 'TERMINATE_CLUSTER', 'CANCEL_AND_WAIT', 'CONTINUE'
        :return: Step ID
        """
        region: str = self._session.region_name
        logger.info(f"region: {region}")
        step = {
            "Name": name,
            "ActionOnFailure": action_on_failure,
            "HadoopJarStep": {
                "Jar": f"s3://{region}.elasticmapreduce/libs/script-runner/script-runner.jar",
                "Args": cmd.split(" ")
            }
        }
        response: Dict = self._client_emr.add_job_flow_steps(JobFlowId=cluster_id, Steps=[step])
        logger.info(f"response: \n{json.dumps(response, default=str, indent=4)}")
        return response["StepIds"][0]

    def get_step_state(self, cluster_id: str, step_id: str) -> str:
        """
        Get the EMR step state
        Possible states: 'PENDING', 'CANCEL_PENDING', 'RUNNING', 'COMPLETED', 'CANCELLED', 'FAILED', 'INTERRUPTED',
        :param cluster_id: EMR Cluster ID
        :param step_id: EMR Step ID
        :return: State (string)
        """
        response: Dict = self._client_emr.describe_step(ClusterId=cluster_id, StepId=step_id)
        logger.info(f"response: \n{json.dumps(response, default=str, indent=4)}")
        return response["Step"]["Status"]["State"]
