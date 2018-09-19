#!groovy
import groovy.json.JsonOutput
import groovy.json.JsonSlurper

def containerName = "${BUILD_TAG}"

pipeline {
    agent {
      label 'av'
    }

    environment {
      GITHUB_TOKEN = credentials('av-github-token')
    }
    stages {
        stage('Notify Github about pending job') {
            steps {
                notifyGithub("pending", "The build has started..")
            }
        }
        stage('Run ansible') {
            steps {
                echo 'Running ansible...'
                script {
                  try {
                    sh "lxc launch ubuntu:16.04 ${containerName}"
                    sh "lxc exec ${containerName} -- sh -c \"until test -f /var/lib/cloud/instance/boot-finished; do sleep 1; done\""
                  }
                  catch (err){
                    currentBuild.result = "FAILURE"
                  }
                  finally {
                    sh "lxc stop ${containerName}"
                  }
                }
            }
        }
        stage('Notify Github about finished job') {
            steps {
              script {
                def build_status = currentBuild.result
                def status
                if ( build_status == 'SUCCESS' ){
                  notifyGithub('success', 'The build succeeded!' )
                }
                else {
                  notifyGithub('failure', 'The build failed :(')
                }
              }
            }
        }

        stage('Cleanup'){
          steps {
            script {
              sh 'lxc delete ${containerName}'
            }
          }
        }
    }
}


def notifyGithub(state, description){
  def githubURL = "https://api.github.com/repos/vrk-kpa/opendata/statuses/$GIT_COMMIT?access_token=$GITHUB_TOKEN"
  def payload = JsonOutput.toJson([
    state: state,
    description: description,
    target_url: "https://vrk-jenkins.eden.csc.fi/job/av/job/av-pipeline/job/$BRANCH_NAME/$BUILD_NUMBER/console",
    context: "continuous-integration/jenkins"
  ])

  sh "curl -X POST -H 'Content-Type: application/json' -d \'${payload}\' ${githubURL}"
}
